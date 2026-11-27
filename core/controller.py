from collections import deque
from datetime import datetime
import logging
import os
from threading import Lock, Thread
import time
import uuid
import config
from core.state import state as default_state

IDLE_AWAY_SECONDS = float(getattr(config, "IDLE_AWAY_SECONDS", 60.0))
MAX_MSG_CHARS = config.MAX_MESSAGE_LENGTH
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
        self._pending_messages = {}
        self._chat_jobs = {}
        self._chat_lock = Lock()
        self._closing = False

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

    def _maybe_auto_select_latest_peer(self, connected_peer=None):
        with self.state.lock:
            if self.state.active_peer_id is not None:
                return
            latest_pid = connected_peer or max(
                (pid for pid in self.state.last_activity if self.state.chat_history.get(pid)),
                key=self.state.last_activity.get,
                default=None,
            )
        if latest_pid is not None:
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

        self.main_window.chat_panel.hide_error()
        self.main_window.chat_panel.set_header(
            f"Đang chat với: {peer_name}", status=peer_status
        )
        self.main_window.chat_panel.set_current_input(restored_draft)
        self.main_window.chat_panel.render_messages(history)
        self.main_window.refresh_sidebar()
        self._queue_chat(pid)

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

    def _queue_chat(self, peer_id, send=None, msg_obj=None, args=()):
        if self.tcp_service is None or self.event_bus is None:
            if msg_obj is not None:
                self._mark_unsent(peer_id, msg_obj)
            return

        with self._chat_lock:
            if self._closing:
                return
            msg_id = msg_obj["msg_id"] if msg_obj is not None else None
            if msg_id is not None:
                self._pending_messages[msg_id] = msg_obj
            if peer_id in self._chat_jobs:
                if send is not None:
                    self._chat_jobs[peer_id].append((send, msg_id, args))
                return
            self._chat_jobs[peer_id] = deque([(send, msg_id, args)])

        Thread(target=self._drain_chat_jobs, args=(peer_id,), daemon=True).start()

    def _drain_chat_jobs(self, peer_id):
        while True:
            with self._chat_lock:
                jobs = self._chat_jobs.get(peer_id)
                if not jobs or self._closing:
                    self._chat_jobs.pop(peer_id, None)
                    return
                send, msg_id, args = jobs.popleft()

            sent = False
            try:
                self.tcp_service.open_chat(peer_id)
                if send is not None:
                    sent = getattr(self.tcp_service, send)(peer_id, *args)
            except Exception:
                logging.exception("Chat operation failed for peer %s", peer_id)
            if msg_id is not None:
                self.event_bus.publish("outgoing_chat_result", {
                    "msg_id": msg_id, "peer_id": peer_id, "sent": sent,
                })

    def send_text_message(self, text: str):
        self.record_user_activity(auto_back_online=True)
        if len(text) > MAX_MSG_CHARS:
            self.main_window.chat_panel.show_error(
                f"Cảnh báo: Tin nhắn vượt quá giới hạn {MAX_MSG_CHARS} ký tự."
            )
            return

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

        self.main_window.chat_panel.append_single_message(msg_obj)
        self.main_window.refresh_sidebar()
        self._queue_chat(active_id, "send_message", msg_obj, (text,))

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

        self.main_window.chat_panel.append_single_message(msg_obj)
        self.main_window.refresh_sidebar()
        self._queue_chat(active_id, "send_sticker", msg_obj, (pack, sticker_id))

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

    def process_event(self, event):
        etype, data = _unpack_event(event)
        if not etype:
            return

        if etype in (
            "peer_updated",
            getattr(config, "EVENT_PEER_UPDATED", "peer_updated"),
        ) or (etype == "chat_connected" and data.get("ip")):
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
            self._maybe_auto_select_latest_peer(pid if etype == "chat_connected" else None)
            self.main_window.refresh_sidebar()

        elif etype in (
            "peer_offline",
            getattr(config, "EVENT_PEER_OFFLINE", "peer_offline"),
            "chat_disconnected",
        ):
            raw_pid = data.get("peer_id")
            if not raw_pid:
                return
            pid = str(raw_pid)
            if self.udp_service and self.udp_service.get_peer(pid):
                return
            if self.tcp_service and self.tcp_service.get_chat_peer(pid):
                return
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

        elif etype == "outgoing_chat_result":
            msg = self._pending_messages.pop(data["msg_id"], None)
            if msg is None:
                return
            pid = data["peer_id"]
            if data["sent"]:
                msg["acked"] = True
                msg["delivery_status"] = "Đã gửi"
                self.main_window.safe_update_status(pid, msg["msg_id"], "Đã gửi")
            else:
                self._mark_unsent(pid, msg)

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
            if is_active:
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
                history = list(self.state.chat_history.get(pid, [])) if is_active and direction == "receive" else []

            if is_active:
                if direction == "receive":
                    self.main_window.chat_panel.render_messages(history)
                elif msg_obj:
                    self.main_window.chat_panel.update_message_status(msg_obj["msg_id"], "Đã gửi")
                self.main_window.chat_panel.update_progress(1.0, f"Hoàn tất {fname}")

        elif etype in (
            "transfer_failed",
            getattr(config, "EVENT_TRANSFER_FAILED", "transfer_failed"),
        ):
            tid = data.get("transfer_id")
            reason = data.get("reason") or "Truyền tệp thất bại"

            with self.state.lock:
                tr = self.state.transfers.get(tid, {})
                raw_pid = data.get("peer_id") or tr.get("peer_id")
                pid = str(raw_pid) if raw_pid else None
                msg_obj = tr.get("msg_obj")
                if msg_obj:
                    msg_obj["delivery_status"] = "Chưa gửi được"
                is_active = pid == self.state.active_peer_id

            if msg_obj and msg_obj.get("msg_id") and is_active:
                self.main_window.chat_panel.update_message_status(
                    msg_obj["msg_id"], "Chưa gửi được"
                )
            if is_active:
                self.main_window.chat_panel.update_progress(1.0, "Lỗi truyền tệp")
                self.main_window.chat_panel.show_error(f"Cảnh báo: {reason}")

        elif etype == "operation_failed":
            with self.state.lock:
                active_id = self.state.active_peer_id
            if data.get("peer_id") and data["peer_id"] != active_id:
                return
            reason = data.get("reason") or "Thao tác thất bại"
            self.main_window.chat_panel.show_error(f"Cảnh báo: {reason}")

    def shutdown(self):
        with self._chat_lock:
            self._closing = True
            self._chat_jobs.clear()
        self._pending_messages.clear()
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
