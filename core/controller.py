from datetime import datetime
import os
import time
import uuid
import config
from core.state import state as default_state
from ui.chat_panel import _get_downloads_dir

SEND_ACK_TIMEOUT = 8.0
IDLE_AWAY_SECONDS = float(getattr(config, "IDLE_AWAY_SECONDS", 60.0))
MAX_MSG_CHARS = 4000
TYPE_MSG = getattr(config, "TYPE_MSG", "MSG")
TYPE_STICKER = getattr(config, "TYPE_STICKER", "STICKER")
TYPE_IMAGE = getattr(config, "TYPE_IMAGE", "IMAGE")
TYPE_FILE = getattr(config, "TYPE_FILE", "FILE")


def _unpack_event(event) -> tuple[str, dict]:
    if isinstance(event, dict):
        etype = event.get("name") or event.get("type") or ""
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = event.get("data") if isinstance(event.get("data"), dict) else {}
        return str(etype), dict(payload)

    etype = getattr(event, "name", None) or getattr(event, "type", None) or ""
    payload = getattr(event, "payload", None)
    if not isinstance(payload, dict):
        payload = getattr(event, "data", None)
    if not isinstance(payload, dict):
        payload = {}
    return str(etype), dict(payload)


class Controller:
    def __init__(self, main_window, app_state=None, event_bus=None):
        self.main_window = main_window
        self.state = app_state or default_state
        self.event_bus = event_bus
        self.udp_service = None
        self.tcp_service = None
        self.file_service = None
        self._pending_by_peer = {}
        self._send_timeout_ids = set()
        self._auto_selected_latest = False
        self._last_text_send = None

    def bind_services(self, udp_service, tcp_service, file_service):
        self.udp_service = udp_service
        self.tcp_service = tcp_service
        self.file_service = file_service
        with self.state.lock:
            st = self.state.my_status
        if self.udp_service and hasattr(self.udp_service, "set_status"):
            try:
                self.udp_service.set_status(st)
            except Exception:
                pass

    def has_active_peer(self) -> bool:
        with self.state.lock:
            return self.state.active_peer_id is not None

    def record_user_activity(self, auto_back_online: bool = True):
        now = time.time()
        changed_to_online = False
        with self.state.lock:
            self.state.last_user_action_ts = now
            if auto_back_online and self.state.my_status == "away":
                self.state.my_status = "online"
                changed_to_online = True
        if changed_to_online:
            self._push_status_to_network("online")
            self.main_window.sidebar.set_my_status("online")

    def check_idle_away(self):
        now = time.time()
        changed_to_away = False
        with self.state.lock:
            last_ts = getattr(self.state, "last_user_action_ts", now)
            elapsed = now - float(last_ts or now)
            if elapsed >= IDLE_AWAY_SECONDS and self.state.my_status != "away":
                self.state.my_status = "away"
                changed_to_away = True
        if changed_to_away:
            self._push_status_to_network("away")
            self.main_window.sidebar.set_my_status("away")

    def set_activity_status(self, new_status: str):
        st = "away" if (new_status or "").lower() == "away" else "online"
        with self.state.lock:
            self.state.my_status = st
            if st == "online":
                self.state.last_user_action_ts = time.time()
        self._push_status_to_network(st)
        self.main_window.sidebar.set_my_status(st)

    def _push_status_to_network(self, status: str):
        if self.udp_service and hasattr(self.udp_service, "set_status"):
            try:
                self.udp_service.set_status(status)
            except Exception:
                pass

    def _touch_activity(self, peer_id: str, ts: float | None = None):
        if peer_id:
            self.state.last_activity[peer_id] = float(
                ts if ts is not None else time.time()
            )

    def _maybe_auto_select_latest_peer(self):
        if self._auto_selected_latest:
            return
        with self.state.lock:
            if self.state.active_peer_id is not None:
                self._auto_selected_latest = True
                return
            candidates = [
                pid
                for pid, ts in self.state.last_activity.items()
                if ts > 0 and len(self.state.chat_history.get(pid, [])) > 0
            ]
            if not candidates:
                return
            latest_pid = max(
                candidates, key=lambda k: self.state.last_activity.get(k, 0.0)
            )
        self._auto_selected_latest = True
        self.select_peer(latest_pid)

    def select_peer(self, new_peer_id: str):
        if not new_peer_id:
            return
        self.record_user_activity(auto_back_online=True)
        self.main_window.hide_sticker_popup()

        pid = str(new_peer_id)
        current_input = self.main_window.chat_panel.get_current_input()

        with self.state.lock:
            if self.state.active_peer_id:
                self.state.drafts[self.state.active_peer_id] = current_input

            self.state.active_peer_id = pid
            self.state.unread_counts[pid] = 0
            restored_draft = self.state.drafts.get(pid, "")
            peer_info = self.state.peers.get(pid, {})
            peer_name = peer_info.get("name") or peer_info.get("peer_name") or "Unknown"
            peer_status = peer_info.get("status", "online")

            history = list(self.state.chat_history.get(pid, []))
            for m in history:
                if m.get("is_me") and m.get("delivery_status") in ("Đã gửi", "Đã nhận"):
                    m["delivery_status"] = "Đã xem"

        if self.tcp_service and hasattr(self.tcp_service, "open_chat"):
            try:
                self.tcp_service.open_chat(pid)
            except Exception as err:
                self.main_window.chat_panel.show_error(f"Cảnh báo: {err}")

        self.main_window.chat_panel.set_header(
            f"Đang chat với: {peer_name}", status=peer_status
        )
        self.main_window.chat_panel.set_current_input(restored_draft)
        self.main_window.chat_panel.render_messages(history)
        self.main_window.refresh_sidebar()

    def change_my_name(self, new_name: str):
        clean_name = (new_name or "").strip()
        if not clean_name:
            return
        self.record_user_activity(auto_back_online=True)
        with self.state.lock:
            self.state.my_name = clean_name

        for svc in (self.udp_service, self.tcp_service):
            if svc is None:
                continue
            for attr in ("peer_name", "my_name", "name"):
                if hasattr(svc, attr):
                    try:
                        setattr(svc, attr, clean_name)
                    except Exception:
                        pass
            for fn_name in ("set_name", "update_name", "set_peer_name"):
                fn = getattr(svc, fn_name, None)
                if callable(fn):
                    try:
                        fn(clean_name)
                    except Exception:
                        pass

        self.main_window.title(f"Furina Chat — {clean_name}")
        self.main_window.sidebar.set_my_name(clean_name)

    def _mark_unsent(self, peer_id: str, msg_obj: dict):
        if msg_obj.get("acked") or msg_obj.get("delivery_status") in (
            "Đã gửi",
            "Đã nhận",
            "Đã xem",
        ):
            return
        msg_obj["delivery_status"] = "Chưa gửi được"
        self.main_window.safe_update_status(peer_id, msg_obj["msg_id"], "Chưa gửi được")

    def _schedule_unsent_timeout(self, peer_id: str, msg_obj: dict, timeout: float):
        def _timer():
            self._send_timeout_ids.discard(after_id)
            self._mark_unsent(peer_id, msg_obj)

        after_id = self.main_window.after(round(timeout * 1000), _timer)
        self._send_timeout_ids.add(after_id)

    def _dispatch_send(
        self, peer_id: str, msg_obj: dict, fn_names: tuple, args: tuple, timeout: float
    ):
        self._schedule_unsent_timeout(peer_id, msg_obj, timeout)
        for svc in (self.tcp_service, self.file_service):
            if svc is None:
                continue
            for fn_name in fn_names:
                fn = getattr(svc, fn_name, None)
                if callable(fn):
                    try:
                        res = fn(*args)
                        if res is False:
                            self._mark_unsent(peer_id, msg_obj)
                        return res
                    except Exception:
                        self._mark_unsent(peer_id, msg_obj)
                        return None
        return None

    def send_text_message(self, text: str):
        self.record_user_activity(auto_back_online=True)
        if len(text) > MAX_MSG_CHARS:
            self.main_window.chat_panel.show_error(
                f"Cảnh báo: Tin nhắn vượt quá giới hạn {MAX_MSG_CHARS} ký tự."
            )
            return

        now_ts = time.time()
        with self.state.lock:
            active_id = self.state.active_peer_id
            my_id = self.state.my_peer_id
            my_name = self.state.my_name
            last_send = getattr(self, "_last_text_send", None)
            if (
                last_send
                and last_send[0] == active_id
                and last_send[1] == text
                and (now_ts - last_send[2]) < 0.5
            ):
                return
            self._last_text_send = (active_id, text, now_ts)

        if not active_id:
            return

        msg_id = str(uuid.uuid4())
        now_str = datetime.now().strftime("%H:%M")
        msg_obj = {
            "msg_id": msg_id,
            "sender_id": my_id,
            "sender_name": my_name,
            "text": text,
            "type": TYPE_MSG,
            "timestamp": now_str,
            "is_me": True,
            "acked": False,
            "delivery_status": "Đang gửi...",
        }

        with self.state.lock:
            self.state.chat_history.setdefault(active_id, []).append(msg_obj)
            self.state.drafts[active_id] = ""
            self._touch_activity(active_id)
        self._pending_by_peer.setdefault(active_id, []).append(msg_obj)

        self.main_window.chat_panel.append_single_message(msg_obj)
        self.main_window.refresh_sidebar()
        self._dispatch_send(
            active_id,
            msg_obj,
            ("send_message", "send_text"),
            (active_id, text),
            SEND_ACK_TIMEOUT,
        )

    def send_sticker(self, pack: str, sticker_id: str):
        self.record_user_activity(auto_back_online=True)
        with self.state.lock:
            active_id = self.state.active_peer_id
            my_id = self.state.my_peer_id
            my_name = self.state.my_name

        if not active_id:
            return

        msg_id = str(uuid.uuid4())
        now_str = datetime.now().strftime("%H:%M")
        msg_obj = {
            "msg_id": msg_id,
            "sender_id": my_id,
            "sender_name": my_name,
            "pack": pack,
            "sticker_id": sticker_id,
            "type": TYPE_STICKER,
            "timestamp": now_str,
            "is_me": True,
            "acked": False,
            "delivery_status": "Đang gửi...",
        }

        with self.state.lock:
            self.state.chat_history.setdefault(active_id, []).append(msg_obj)
            self._touch_activity(active_id)
        self._pending_by_peer.setdefault(active_id, []).append(msg_obj)

        self.main_window.chat_panel.append_single_message(msg_obj)
        self.main_window.refresh_sidebar()
        self._dispatch_send(
            active_id,
            msg_obj,
            ("send_sticker",),
            (active_id, pack, sticker_id),
            SEND_ACK_TIMEOUT,
        )

    def send_file(self, file_path: str, media_type: str = TYPE_FILE):
        self.record_user_activity(auto_back_online=True)
        if not file_path or not os.path.isfile(file_path):
            self.main_window.chat_panel.show_error(
                "Cảnh báo: Không tìm thấy tệp hoặc tệp không tồn tại."
            )
            return

        with self.state.lock:
            active_id = self.state.active_peer_id
            my_id = self.state.my_peer_id
            my_name = self.state.my_name

        if not active_id:
            return

        norm_type = TYPE_IMAGE if str(media_type).upper() == TYPE_IMAGE else TYPE_FILE
        msg_id = str(uuid.uuid4())
        fname = os.path.basename(file_path)
        fsize = os.path.getsize(file_path)
        now_str = datetime.now().strftime("%H:%M")

        msg_obj = {
            "msg_id": msg_id,
            "sender_id": my_id,
            "sender_name": my_name,
            "type": norm_type,
            "filename": fname,
            "filepath": file_path,
            "local_path": file_path,
            "size": fsize,
            "timestamp": now_str,
            "is_me": True,
            "acked": False,
            "delivery_status": "Đang gửi...",
        }

        with self.state.lock:
            self.state.chat_history.setdefault(active_id, []).append(msg_obj)
            self._touch_activity(active_id)
        self._pending_by_peer.setdefault(active_id, []).append(msg_obj)

        self.main_window.chat_panel.append_single_message(msg_obj)
        self.main_window.refresh_sidebar()

        try:
            send_file = getattr(self.file_service, "send_file", None)
            tid = send_file(active_id, file_path, norm_type) if send_file else None
        except Exception:
            self._mark_unsent(active_id, msg_obj)
            return

        if not tid:
            self._mark_unsent(active_id, msg_obj)
            return

        with self.state.lock:
            self.state.transfers[tid] = {
                "transfer_id": tid,
                "peer_id": active_id,
                "direction": "send",
                "filename": fname,
                "total_bytes": fsize,
                "bytes_done": 0,
                "msg_obj": msg_obj,
            }

    def _cleanup_failed_transfer_files(self, fname: str, local_path: str = ""):
        dl_dir = _get_downloads_dir()
        candidates = set()
        if local_path:
            candidates.add(local_path)
            candidates.add(local_path + ".part")
        if fname and os.path.isdir(dl_dir):
            base_target = os.path.join(dl_dir, os.path.basename(fname))
            candidates.add(base_target + ".part")
            for entry in os.listdir(dl_dir):
                if entry.endswith(".part") and (
                    not fname or os.path.basename(fname) in entry
                ):
                    candidates.add(os.path.join(dl_dir, entry))

        for path in candidates:
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def process_event(self, event):
        etype, data = _unpack_event(event)
        if not etype:
            return

        if etype in (
            "peer_updated",
            getattr(config, "EVENT_PEER_UPDATED", "peer_updated"),
        ):
            raw_pid = data.get("peer_id")
            if not raw_pid:
                return
            pid = str(raw_pid)
            with self.state.lock:
                existing = dict(self.state.peers.get(pid, {}))
                existing.update({k: v for k, v in data.items() if v is not None})
                existing["peer_id"] = pid
                if not existing.get("name") and existing.get("peer_name"):
                    existing["name"] = existing["peer_name"]
                raw_st = (existing.get("status") or "online").lower()
                existing["status"] = "away" if raw_st == "away" else "online"
                self.state.peers[pid] = existing
                self.state.chat_history.setdefault(pid, [])
                is_active = pid == self.state.active_peer_id
                peer_name = existing.get("name") or existing.get("peer_name") or "Unknown"
                peer_status = existing.get("status", "online")

            remember_peer = getattr(self.file_service, "remember_peer", None)
            if remember_peer:
                remember_peer(pid, existing.get("ip"), existing.get("tcp_port"))

            if is_active:
                self.main_window.chat_panel.set_header(
                    f"Đang chat với: {peer_name}", status=peer_status
                )
            self._maybe_auto_select_latest_peer()
            self.main_window.refresh_sidebar()

        elif etype in (
            "peer_offline",
            getattr(config, "EVENT_PEER_OFFLINE", "peer_offline"),
        ):
            raw_pid = data.get("peer_id")
            if not raw_pid:
                return
            pid = str(raw_pid)
            with self.state.lock:
                existing = dict(self.state.peers.get(pid, {}))
                existing["peer_id"] = pid
                if not existing.get("name"):
                    existing["name"] = data.get("name") or "Peer"
                existing["status"] = "offline"
                self.state.peers[pid] = existing
                self.state.chat_history.setdefault(pid, [])
                is_active = pid == self.state.active_peer_id
                peer_name = existing.get("name") or "Unknown"

            if is_active:
                self.main_window.chat_panel.set_header(
                    f"Đang chat với: {peer_name}", status="offline"
                )
            self.main_window.refresh_sidebar()

        elif etype in ("message_sent", "sticker_sent"):
            raw_pid = data.get("peer_id")
            pid = str(raw_pid) if raw_pid else None
            if data.get("error") or data.get("failed"):
                pending = self._pending_by_peer.get(pid, [])
                for m in reversed(pending):
                    if not m.get("acked"):
                        self._mark_unsent(pid, m)
                        break
                return

            pending = self._pending_by_peer.get(pid, [])
            for m in reversed(pending):
                if not m.get("acked"):
                    m["acked"] = True
                    m["delivery_status"] = "Đã gửi"
                    self.main_window.safe_update_status(pid, m["msg_id"], "Đã gửi")
                    break

        elif etype in ("message_received", "sticker_received"):
            raw_pid = data.get("peer_id")
            if not raw_pid:
                return
            pid = str(raw_pid)
            raw_msg = (
                dict(data["message"])
                if isinstance(data.get("message"), dict)
                else dict(data)
            )
            msg = {
                "msg_id": raw_msg.get("msg_id") or str(uuid.uuid4()),
                "sender_name": raw_msg.get("sender_name")
                or raw_msg.get("sender")
                or self.state.peers.get(pid, {}).get("name", "Peer"),
                "text": raw_msg.get("text", ""),
                "pack": raw_msg.get("pack", "cat"),
                "sticker_id": raw_msg.get("sticker_id", ""),
                "type": raw_msg.get("type")
                or (TYPE_STICKER if etype == "sticker_received" else TYPE_MSG),
                "timestamp": raw_msg.get("timestamp")
                or datetime.now().strftime("%H:%M"),
                "is_me": False,
                "delivery_status": "Đã nhận",
            }

            with self.state.lock:
                self.state.peers.setdefault(
                    pid,
                    {
                        "peer_id": pid,
                        "name": msg["sender_name"],
                        "status": getattr(config, "STATUS_ONLINE", "online"),
                    },
                )
                self.state.chat_history.setdefault(pid, []).append(msg)
                self._touch_activity(pid)
                is_active = pid == self.state.active_peer_id
                if not is_active:
                    self.state.unread_counts[pid] = (
                        self.state.unread_counts.get(pid, 0) + 1
                    )

            self._maybe_auto_select_latest_peer()
            with self.state.lock:
                is_active_now = pid == self.state.active_peer_id

            if is_active_now:
                self.main_window.chat_panel.append_single_message(msg)
            self.main_window.refresh_sidebar()

        elif etype in (
            "transfer_started",
            getattr(config, "EVENT_TRANSFER_STARTED", "transfer_started"),
        ):
            tid = data.get("transfer_id")
            raw_pid = data.get("peer_id")
            pid = str(raw_pid) if raw_pid else None
            direction = data.get("direction", "receive")
            fname = data.get("filename", "file")
            total_bytes = int(data.get("total_bytes") or 0)
            mtype = (
                data.get("media_type")
                or (
                    TYPE_IMAGE
                    if fname.lower().endswith(
                        (".png", ".jpg", ".jpeg", ".gif", ".webp")
                    )
                    else TYPE_FILE
                )
            ).upper()

            with self.state.lock:
                tr = self.state.transfers.setdefault(tid, {"transfer_id": tid})
                tr.update(
                    {
                        "peer_id": pid,
                        "direction": direction,
                        "filename": fname,
                        "total_bytes": total_bytes,
                        "bytes_done": 0,
                    }
                )
                if pid:
                    self._touch_activity(pid)
                is_active = pid == self.state.active_peer_id
                if direction == "receive" and pid:
                    rec = {
                        "msg_id": str(uuid.uuid4()),
                        "sender_name": self.state.peers.get(pid, {}).get("name", "Peer"),
                        "type": mtype,
                        "filename": fname,
                        "size": total_bytes,
                        "timestamp": datetime.now().strftime("%H:%M"),
                        "is_me": False,
                        "delivery_status": "Đang nhận...",
                    }
                    tr["msg_obj"] = rec
                    self.state.chat_history.setdefault(pid, []).append(rec)
                    if not is_active:
                        self.state.unread_counts[pid] = (
                            self.state.unread_counts.get(pid, 0) + 1
                        )

            self._maybe_auto_select_latest_peer()
            with self.state.lock:
                is_active_now = pid == self.state.active_peer_id

            if is_active_now and direction == "receive" and tr.get("msg_obj"):
                self.main_window.chat_panel.append_single_message(tr["msg_obj"])
            self.main_window.refresh_sidebar()

        elif etype in (
            "transfer_progress",
            getattr(config, "EVENT_TRANSFER_PROGRESS", "transfer_progress"),
        ):
            tid = data.get("transfer_id")
            with self.state.lock:
                tr = self.state.transfers.get(tid, {})
                raw_pid = data.get("peer_id") or tr.get("peer_id")
                pid = str(raw_pid) if raw_pid else None
                fname = data.get("filename") or tr.get("filename") or "file"
                total = int(data.get("total_bytes") or tr.get("total_bytes") or 0)
                done = int(data.get("bytes_done") or tr.get("bytes_done") or 0)
                if "percent" in data and data["percent"] is not None:
                    pct = float(data["percent"])
                elif total > 0:
                    pct = done / total
                else:
                    pct = 1.0
                is_active = pid == self.state.active_peer_id

            if is_active:
                text = (
                    data.get("status_text")
                    or f"Truyền {fname}: {int(max(0.0, min(1.0, pct)) * 100)}%"
                )
                self.main_window.chat_panel.update_progress(pct, text)

        elif etype in (
            "transfer_finished",
            getattr(config, "EVENT_TRANSFER_FINISHED", "transfer_finished"),
        ):
            tid = data.get("transfer_id")
            fname = data.get("filename") or "file"
            local_path = data.get("local_path") or ""

            with self.state.lock:
                tr = self.state.transfers.get(tid, {})
                raw_pid = data.get("peer_id") or tr.get("peer_id")
                pid = str(raw_pid) if raw_pid else None
                direction = data.get("direction") or tr.get("direction") or "send"
                msg_obj = tr.get("msg_obj")
                if msg_obj:
                    if local_path:
                        msg_obj["local_path"] = local_path
                        msg_obj["filepath"] = local_path
                    msg_obj["acked"] = True
                    msg_obj["delivery_status"] = (
                        "Đã gửi" if direction == "send" else "Đã nhận"
                    )
                is_active = pid == self.state.active_peer_id
                history = list(self.state.chat_history.get(pid, [])) if is_active else []

            if is_active:
                self.main_window.chat_panel.render_messages(history)
                self.main_window.chat_panel.update_progress(1.0, f"Hoàn tất {fname}")

        elif etype in (
            "transfer_failed",
            getattr(config, "EVENT_TRANSFER_FAILED", "transfer_failed"),
        ):
            tid = data.get("transfer_id")
            reason = data.get("reason") or "Truyền tệp thất bại"
            local_path = data.get("local_path") or ""

            with self.state.lock:
                tr = self.state.transfers.get(tid, {})
                raw_pid = data.get("peer_id") or tr.get("peer_id")
                pid = str(raw_pid) if raw_pid else None
                fname = data.get("filename") or tr.get("filename") or ""
                msg_obj = tr.get("msg_obj")
                if msg_obj:
                    msg_obj["delivery_status"] = "Chưa gửi được"
                is_active = pid == self.state.active_peer_id

            self._cleanup_failed_transfer_files(fname, local_path=local_path)

            if msg_obj and msg_obj.get("msg_id") and is_active:
                self.main_window.chat_panel.update_message_status(
                    msg_obj["msg_id"], "Chưa gửi được"
                )
            if is_active:
                self.main_window.chat_panel.update_progress(1.0, "Lỗi truyền tệp")
                self.main_window.chat_panel.show_error(f"Cảnh báo: {reason}")

        elif etype in ("send_failed", "message_failed"):
            raw_pid = data.get("peer_id")
            pid = str(raw_pid) if raw_pid else None
            pending = self._pending_by_peer.get(pid, [])
            for m in reversed(pending):
                if not m.get("acked"):
                    self._mark_unsent(pid, m)
                    break

        elif etype == "operation_failed":
            reason = data.get("reason") or "Thao tác thất bại"
            self.main_window.chat_panel.show_error(f"Cảnh báo: {reason}")

    def shutdown(self):
        for after_id in self._send_timeout_ids:
            self.main_window.after_cancel(after_id)
        self._send_timeout_ids.clear()
        if self.file_service and hasattr(self.file_service, "stop"):
            try:
                self.file_service.stop()
            except Exception:
                pass
        if self.tcp_service and hasattr(self.tcp_service, "stop"):
            try:
                self.tcp_service.stop()
            except Exception:
                pass
        if self.udp_service and hasattr(self.udp_service, "stop"):
            try:
                self.udp_service.stop()
            except Exception:
                pass
