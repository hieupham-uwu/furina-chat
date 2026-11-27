from datetime import datetime
import os
import threading
import time
import uuid
from core.state import state

# Sau khoảng thời gian này mà chưa gửi/xác nhận được do lỗi mạng thì mới hiện "Chưa gửi được"
SEND_ACK_TIMEOUT = 5.0
FILE_ACK_TIMEOUT = 15.0


class Controller:
    def __init__(self, main_window, standalone_demo: bool = True):
        self.main_window = main_window
        self.standalone_demo = standalone_demo
        self.udp_service = None
        self.tcp_service = None
        self.file_service = None
        self._pending_by_peer = {}  # {peer_id: [msg_obj, ...]}

    def bind_services(self, udp_service, tcp_service, file_service):
        self.udp_service = udp_service
        self.tcp_service = tcp_service
        self.file_service = file_service

    def has_active_peer(self) -> bool:
        with state.lock:
            return state.active_peer_id is not None

    def select_peer(self, new_peer_id: str):
        current_input = self.main_window.chat_panel.get_current_input()
        self.main_window.chat_panel.sticker_popup.hide_popup()

        with state.lock:
            if state.active_peer_id:
                state.drafts[state.active_peer_id] = current_input

            state.active_peer_id = new_peer_id
            state.unread_counts[new_peer_id] = 0
            restored_draft = state.drafts.get(new_peer_id, "")
            peer_info = state.peers.get(new_peer_id, {})
            peer_name = peer_info.get("name", "Unknown")
            peer_status = peer_info.get("status", "offline")

            history = list(state.chat_history.get(new_peer_id, []))
            for m in history:
                if m.get("is_me") and m.get("delivery_status") in ("Đã gửi", "Đã nhận"):
                    m["delivery_status"] = "Đã xem"

        if self.tcp_service and hasattr(self.tcp_service, "open_chat"):
            try:
                self.tcp_service.open_chat(new_peer_id)
            except Exception:
                pass

        self.main_window.chat_panel.set_header(
            f"Chat với: {peer_name}", status=peer_status
        )
        self.main_window.chat_panel.set_current_input(restored_draft)
        self.main_window.chat_panel.render_messages(history)
        self.main_window.refresh_sidebar()

    def change_status(self, new_status: str):
        with state.lock:
            state.my_status = new_status
        if self.udp_service and hasattr(self.udp_service, "set_status"):
            try:
                self.udp_service.set_status(new_status)
            except Exception:
                pass

    def _schedule_unsent_timeout(self, peer_id: str, msg_obj: dict, timeout: float):
        """Chỉ chuyển sang 'Chưa gửi được' khi quá thời gian quy định mà vẫn chưa gửi/xác nhận được."""
        def _timer():
            time.sleep(timeout)
            if msg_obj.get("acked") or msg_obj.get("delivery_status") in (
                "Đã gửi",
                "Đã nhận",
                "Đã xem",
            ):
                return
            msg_obj["delivery_status"] = "Chưa gửi được"
            self.main_window.safe_update_status(
                peer_id, msg_obj["msg_id"], "Chưa gửi được"
            )

        threading.Thread(target=_timer, daemon=True).start()

    def _simulate_local_send(self, peer_id: str, msg_obj: dict, is_file: bool = False):
        def _worker():
            if is_file:
                for step in (0.25, 0.5, 0.75, 1.0):
                    time.sleep(0.2)
                    self.main_window.safe_progress(
                        peer_id,
                        step,
                        f"Đang gửi {msg_obj.get('filename', 'file')}: {int(step * 100)}%",
                    )
            else:
                time.sleep(0.25)

            msg_obj["acked"] = True
            msg_obj["delivery_status"] = "Đã gửi"
            self.main_window.safe_update_status(peer_id, msg_obj["msg_id"], "Đã gửi")

            time.sleep(0.6)
            msg_obj["delivery_status"] = "Đã nhận"
            self.main_window.safe_update_status(peer_id, msg_obj["msg_id"], "Đã nhận")

        threading.Thread(target=_worker, daemon=True).start()

    def send_text_message(self, text: str):
        if len(text) > 4000:
            text = text[:4000]

        with state.lock:
            active_id = state.active_peer_id
            my_id = state.my_peer_id
            my_name = state.my_name

        if not active_id:
            return

        msg_id = str(uuid.uuid4())
        now_str = datetime.now().strftime("%H:%M")
        msg_obj = {
            "msg_id": msg_id,
            "sender_id": my_id,
            "sender_name": my_name,
            "text": text,
            "type": "MSG",
            "timestamp": now_str,
            "is_me": True,
            "acked": False,
            "delivery_status": "Đang gửi...",
        }

        with state.lock:
            state.chat_history.setdefault(active_id, []).append(msg_obj)
            state.drafts[active_id] = ""
        self._pending_by_peer.setdefault(active_id, []).append(msg_obj)

        self.main_window.chat_panel.append_single_message(msg_obj)
        self._schedule_unsent_timeout(active_id, msg_obj, SEND_ACK_TIMEOUT)

        if self.tcp_service and hasattr(self.tcp_service, "send_message"):
            try:
                self.tcp_service.send_message(active_id, text)
            except Exception:
                self._schedule_unsent_timeout(active_id, msg_obj, SEND_ACK_TIMEOUT)
        elif self.standalone_demo:
            self._simulate_local_send(active_id, msg_obj, is_file=False)

    def send_sticker(self, pack: str, sticker_id: str):
        with state.lock:
            active_id = state.active_peer_id
            my_id = state.my_peer_id
            my_name = state.my_name

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
            "type": "STICKER",
            "timestamp": now_str,
            "is_me": True,
            "acked": False,
            "delivery_status": "Đang gửi...",
        }

        with state.lock:
            state.chat_history.setdefault(active_id, []).append(msg_obj)
        self._pending_by_peer.setdefault(active_id, []).append(msg_obj)

        self.main_window.chat_panel.append_single_message(msg_obj)
        self._schedule_unsent_timeout(active_id, msg_obj, SEND_ACK_TIMEOUT)

        if self.tcp_service and hasattr(self.tcp_service, "send_sticker"):
            try:
                self.tcp_service.send_sticker(active_id, pack, sticker_id)
            except Exception:
                self._schedule_unsent_timeout(active_id, msg_obj, SEND_ACK_TIMEOUT)
        elif self.standalone_demo:
            self._simulate_local_send(active_id, msg_obj, is_file=False)

    def send_file(self, file_path: str, media_type: str = "FILE"):
        if not file_path or not os.path.isfile(file_path):
            self.main_window.chat_panel.show_error("File not found: tệp không tồn tại.")
            return

        with state.lock:
            active_id = state.active_peer_id
            my_id = state.my_peer_id
            my_name = state.my_name

        if not active_id:
            return

        norm_type = "IMAGE" if str(media_type).upper() == "IMAGE" else "FILE"
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

        with state.lock:
            state.chat_history.setdefault(active_id, []).append(msg_obj)
        self._pending_by_peer.setdefault(active_id, []).append(msg_obj)

        self.main_window.chat_panel.append_single_message(msg_obj)
        self._schedule_unsent_timeout(active_id, msg_obj, FILE_ACK_TIMEOUT)

        if self.file_service and hasattr(self.file_service, "send_file"):
            try:
                tid = self.file_service.send_file(active_id, file_path, norm_type)
                if tid:
                    with state.lock:
                        state.transfers[tid] = {
                            "transfer_id": tid,
                            "peer_id": active_id,
                            "direction": "send",
                            "filename": fname,
                            "total_bytes": fsize,
                            "bytes_done": 0,
                            "msg_obj": msg_obj,
                        }
            except Exception:
                self._schedule_unsent_timeout(active_id, msg_obj, FILE_ACK_TIMEOUT)
        elif self.standalone_demo:
            self._simulate_local_send(active_id, msg_obj, is_file=True)

    def leave_chat(self):
        with state.lock:
            active_id = state.active_peer_id
            if not active_id:
                return
            state.drafts[active_id] = self.main_window.chat_panel.get_current_input()
            state.active_peer_id = None

        if self.tcp_service and hasattr(self.tcp_service, "leave_chat"):
            try:
                self.tcp_service.leave_chat(active_id)
            except Exception:
                pass

        self.main_window.chat_panel.set_current_input("")
        self.main_window.chat_panel.render_messages([])
        self.main_window.refresh_sidebar()

    def process_event(self, event: dict):
        etype = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else event

        if etype == "peer_updated":
            pid = data.get("peer_id")
            if not pid:
                return
            with state.lock:
                existing = dict(state.peers.get(pid, {}))
                existing.update({k: v for k, v in data.items() if v is not None})
                existing.setdefault("status", "online")
                state.peers[pid] = existing
            self.main_window.refresh_sidebar()

        elif etype == "peer_offline":
            pid = data.get("peer_id")
            if not pid:
                return
            with state.lock:
                if pid in state.peers:
                    state.peers[pid]["status"] = "offline"
            self.main_window.refresh_sidebar()

        elif etype in ("message_sent", "sticker_sent"):
            pid = data.get("peer_id")
            pending = self._pending_by_peer.get(pid, [])
            for m in reversed(pending):
                if not m.get("acked"):
                    m["acked"] = True
                    m["delivery_status"] = "Đã gửi"
                    self.main_window.safe_update_status(pid, m["msg_id"], "Đã gửi")
                    break

        elif etype in ("message_received", "sticker_received"):
            # Dù peer đang hiển thị là offline trên discovery, vẫn nhận và hiển thị/lưu tin nhắn bình thường
            pid = data.get("peer_id")
            if not pid:
                return
            raw_msg = (
                dict(data["message"])
                if isinstance(data.get("message"), dict)
                else dict(data)
            )
            msg = {
                "msg_id": raw_msg.get("msg_id") or str(uuid.uuid4()),
                "sender_name": raw_msg.get("sender_name")
                or raw_msg.get("sender")
                or state.peers.get(pid, {}).get("name", "Peer"),
                "text": raw_msg.get("text", ""),
                "pack": raw_msg.get("pack", "cat"),
                "sticker_id": raw_msg.get("sticker_id", ""),
                "type": raw_msg.get("type")
                or ("STICKER" if etype == "sticker_received" else "MSG"),
                "timestamp": raw_msg.get("timestamp")
                or datetime.now().strftime("%H:%M"),
                "is_me": False,
                "delivery_status": "Đã nhận",
            }

            with state.lock:
                state.chat_history.setdefault(pid, []).append(msg)
                is_active = pid == state.active_peer_id
                if not is_active:
                    state.unread_counts[pid] = state.unread_counts.get(pid, 0) + 1

            if is_active:
                self.main_window.chat_panel.append_single_message(msg)
            else:
                self.main_window.refresh_sidebar()

        elif etype == "transfer_started":
            tid = data.get("transfer_id")
            pid = data.get("peer_id")
            direction = data.get("direction", "receive")
            fname = data.get("filename", "file")
            total_bytes = int(data.get("total_bytes") or 0)
            mtype = (
                data.get("media_type")
                or (
                    "IMAGE"
                    if fname.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
                    else "FILE"
                )
            ).upper()

            with state.lock:
                tr = state.transfers.setdefault(tid, {"transfer_id": tid})
                tr.update(
                    {
                        "peer_id": pid,
                        "direction": direction,
                        "filename": fname,
                        "total_bytes": total_bytes,
                        "bytes_done": 0,
                    }
                )
                is_active = pid == state.active_peer_id
                if direction == "receive" and pid:
                    rec = {
                        "msg_id": str(uuid.uuid4()),
                        "sender_name": state.peers.get(pid, {}).get("name", "Peer"),
                        "type": mtype,
                        "filename": fname,
                        "size": total_bytes,
                        "timestamp": datetime.now().strftime("%H:%M"),
                        "is_me": False,
                        "delivery_status": "Đang nhận...",
                    }
                    tr["msg_obj"] = rec
                    state.chat_history.setdefault(pid, []).append(rec)
                    if not is_active:
                        state.unread_counts[pid] = state.unread_counts.get(pid, 0) + 1

            if is_active and direction == "receive" and tr.get("msg_obj"):
                self.main_window.chat_panel.append_single_message(tr["msg_obj"])
            elif not is_active:
                self.main_window.refresh_sidebar()

        elif etype == "transfer_progress":
            tid = data.get("transfer_id")
            with state.lock:
                tr = state.transfers.get(tid, {})
                pid = data.get("peer_id") or tr.get("peer_id")
                fname = data.get("filename") or tr.get("filename") or "file"
                total = int(data.get("total_bytes") or tr.get("total_bytes") or 0)
                done = int(data.get("bytes_done") or tr.get("bytes_done") or 0)
                if "percent" in data and data["percent"] is not None:
                    pct = float(data["percent"])
                elif total > 0:
                    pct = done / total
                else:
                    pct = 1.0
                is_active = pid == state.active_peer_id

            if is_active:
                text = (
                    data.get("status_text")
                    or f"Truyền {fname}: {int(max(0.0, min(1.0, pct)) * 100)}%"
                )
                self.main_window.chat_panel.update_progress(pct, text)

        elif etype == "transfer_finished":
            tid = data.get("transfer_id")
            fname = data.get("filename") or "file"
            local_path = data.get("local_path") or ""

            with state.lock:
                tr = state.transfers.get(tid, {})
                pid = data.get("peer_id") or tr.get("peer_id")
                direction = data.get("direction") or tr.get("direction") or "send"
                msg_obj = tr.get("msg_obj")
                if msg_obj:
                    if local_path:
                        msg_obj["local_path"] = local_path
                        msg_obj["filepath"] = local_path
                    msg_obj["acked"] = True
                    msg_obj["delivery_status"] = "Đã gửi" if direction == "send" else "Đã nhận"
                is_active = pid == state.active_peer_id
                history = list(state.chat_history.get(pid, [])) if is_active else []

            if is_active:
                self.main_window.chat_panel.render_messages(history)
                self.main_window.chat_panel.update_progress(1.0, f"Hoàn tất {fname}")

        elif etype == "transfer_failed":
            tid = data.get("transfer_id")
            reason = data.get("reason") or "Truyền tệp thất bại"
            with state.lock:
                tr = state.transfers.get(tid, {})
                pid = data.get("peer_id") or tr.get("peer_id")
                msg_obj = tr.get("msg_obj")
                if msg_obj:
                    msg_obj["delivery_status"] = "Chưa gửi được"
                is_active = pid == state.active_peer_id

            if msg_obj and msg_obj.get("msg_id") and is_active:
                self.main_window.chat_panel.update_message_status(
                    msg_obj["msg_id"], "Chưa gửi được"
                )
            if is_active:
                self.main_window.chat_panel.update_progress(1.0, "Lỗi truyền tệp")
                self.main_window.chat_panel.show_error(reason)

        elif etype == "operation_failed":
            reason = data.get("reason") or "Thao tác thất bại"
            self.main_window.chat_panel.show_error(reason)

    def shutdown(self):
        for svc in (self.tcp_service, self.file_service, self.udp_service):
            if svc and hasattr(svc, "stop"):
                try:
                    svc.stop()
                except Exception:
                    pass