"""
Operator banners, remote alerts, telemetry watchdog, LS370 register check, status tiles and FAA RMS.

Mixin for gui.MyApp (split out of gui.py, P1-12). Methods are unchanged; they use the
MyApp instance (self) and the shared names in gui_common.
"""
from gui_common import *  # noqa: F401,F403
from gui_common import _states_mod  # noqa: F401
import plot_utils


class OperatorAlertDialog(QDialog):
    """
    Centered, always-on-top alert window the operator must answer before using the GUI again.
      - "Action required": a procedure is waiting (world.request_operator_action). Only "Confirm Step Done"
        confirms it.
      - "Notices": warnings, reminders, watchdog/errors. "Acknowledge" clears them and NEVER confirms an action.
    Esc and the window close button do nothing; new messages are added to the open window (no stacking).
    """

    def __init__(self, parent, on_confirm, on_acknowledge):
        super().__init__(parent, Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setWindowTitle("2PAC: operator attention")
        self.setWindowModality(Qt.WindowModal)
        self.setObjectName("operator_alert")
        self.setStyleSheet("""
            QDialog#operator_alert { background-color: #0f172a; border: 3px solid #f59e0b; }
            QLabel { color: #f8fafc; background: transparent; }
            QLabel#hdr_action { color: #fbbf24; font-size: 18px; font-weight: 800; }
            QLabel#hdr_notice { color: #93c5fd; font-size: 16px; font-weight: 800; }
            QLabel#msg { font-size: 15px; font-weight: 600; }
            QLabel#when { color: #94a3b8; font-size: 11px; }
            QFrame#sep { background-color: #334155; max-height: 1px; }
            QPushButton { font-size: 15px; font-weight: 800; border-radius: 6px; padding: 10px 22px; }
            QPushButton#btn_confirm { background-color: #16a34a; color: white; border: 1px solid #15803d; }
            QPushButton#btn_ack { background-color: #2563eb; color: white; border: 1px solid #1d4ed8; }
        """)
        self._allow_close = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

        self.hdr_action = QLabel("⚠️  ACTION REQUIRED: the procedure is waiting for you")
        self.hdr_action.setObjectName("hdr_action")
        self.box_action = QVBoxLayout()
        self.btn_confirm = QPushButton("✔  Confirm Step Done")
        self.btn_confirm.setObjectName("btn_confirm")
        self.btn_confirm.clicked.connect(on_confirm)
        self.sep = QFrame()
        self.sep.setObjectName("sep")
        self.hdr_notice = QLabel("ℹ️  Notices")
        self.hdr_notice.setObjectName("hdr_notice")
        self.box_notice = QVBoxLayout()
        self.btn_ack = QPushButton("Acknowledge")
        self.btn_ack.setObjectName("btn_ack")
        self.btn_ack.clicked.connect(on_acknowledge)

        row_c = QHBoxLayout(); row_c.addStretch(1); row_c.addWidget(self.btn_confirm)
        row_a = QHBoxLayout(); row_a.addStretch(1); row_a.addWidget(self.btn_ack)
        lay.addWidget(self.hdr_action)
        lay.addLayout(self.box_action)
        lay.addLayout(row_c)
        lay.addWidget(self.sep)
        lay.addWidget(self.hdr_notice)
        self.notice_scroll = QScrollArea()
        self.notice_scroll.setWidgetResizable(True)
        self.notice_scroll.setFrameShape(QFrame.NoFrame)
        self.notice_scroll.setStyleSheet("QScrollArea { background: transparent; } QWidget#notice_inner { background: transparent; }")
        inner = QWidget(); inner.setObjectName("notice_inner"); inner.setLayout(self.box_notice)
        self.notice_scroll.setWidget(inner)
        lay.addWidget(self.notice_scroll)
        lay.addLayout(row_a)

    @staticmethod
    def _clear(box):
        while box.count():
            it = box.takeAt(0)
            wdg = it.widget()
            if wdg is not None:
                wdg.hide()             # detach now: deleteLater alone keeps painting until the next event loop pass
                wdg.setParent(None)
                wdg.deleteLater()

    @staticmethod
    def _add_item(box, item):
        when = datetime.fromtimestamp(item["t"]).strftime("%H:%M:%S")
        extra = f"  (×{item['count']}, last {datetime.fromtimestamp(item['t_last']).strftime('%H:%M:%S')})" if item["count"] > 1 else ""
        lw = QLabel(f"{when}{extra}  ·  {item['source']}")
        lw.setObjectName("when")
        lm = QLabel(item["text"])
        lm.setObjectName("msg")
        lm.setWordWrap(True)
        lm.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(lw)
        box.addWidget(lm)

    def set_items(self, actions, notices):
        self._clear(self.box_action)
        self._clear(self.box_notice)
        for it in actions:
            self._add_item(self.box_action, it)
        for it in reversed(notices):          # newest first
            self._add_item(self.box_notice, it)
        self.box_notice.addStretch(1)
        has_a, has_n = bool(actions), bool(notices)
        for w in (self.hdr_action, self.btn_confirm):
            w.setVisible(has_a)
        for w in (self.hdr_notice, self.notice_scroll, self.btn_ack):
            w.setVisible(has_n)
        self.sep.setVisible(has_a and has_n)
        self.hdr_notice.setText(f"ℹ️  Notices ({len(notices)})" if len(notices) > 1 else "ℹ️  Notice")
        self.notice_scroll.setMinimumHeight(min(320, 70 * len(notices)) if has_n else 0)
        self._recenter()

    def _recenter(self):
        par = self.parentWidget()
        if par is None:
            return
        g = par.frameGeometry()
        w = max(520, min(900, int(g.width() * 0.6)))
        self.setFixedWidth(w)
        self.adjustSize()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)

    def present(self):
        if not self.isVisible():
            self.show()
        self._recenter()
        self.raise_()
        self.activateWindow()
        QApplication.beep()

    def close_for_real(self):
        self._allow_close = True
        self.hide()
        self._allow_close = False

    def reject(self):          # Esc
        pass

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        else:
            event.ignore()


class StatusAlertsMixin:

    # ---------------- operator alerts (centered window) ----------------
    def _alert_state(self):
        if not hasattr(self, "_alert_actions"):
            self._alert_actions, self._alert_notices, self._alert_dialog = [], [], None
        return self._alert_actions, self._alert_notices

    def _alert_add(self, kind, text, source="GUI"):
        actions, notices = self._alert_state()
        lst = actions if kind == "action" else notices
        now = time.time()
        for it in lst:
            if it["text"] == text:
                it["count"] += 1
                it["t_last"] = now
                break
        else:
            lst.append({"text": str(text), "t": now, "t_last": now, "count": 1, "source": source})
            del lst[:-30]
        self._alert_refresh(present=True)

    def _alert_refresh(self, present=False):
        actions, notices = self._alert_state()
        if not actions and not notices:
            if self._alert_dialog is not None:
                self._alert_dialog.close_for_real()
            return
        if self._alert_dialog is None:
            self._alert_dialog = OperatorAlertDialog(self, self.confirm_operator_action, self._acknowledge_notices)
        self._alert_dialog.set_items(actions, notices)
        if present or not self._alert_dialog.isVisible():
            self._alert_dialog.present()

    def _acknowledge_notices(self):
        self._alert_state()
        self._alert_notices.clear()
        self._alert_refresh()

    def _clear_alert_actions(self):
        self._alert_state()
        self._alert_actions.clear()
        self._alert_refresh()

    def show_operator_banner(self, text):
        """Every GUI banner is a notice in the centered alert window (acknowledge required)."""
        self._alert_add("notice", text, source="GUI")

    def dismiss_operator_banner(self):
        """Operator started/stopped a procedure: nothing is waiting any more; clear the alert window."""
        self._alert_state()
        self._alert_actions.clear()
        self._alert_notices.clear()
        self._alert_refresh()

    def _on_operator_action(self, state_name, text):
        w = getattr(self, "world", None)
        waiting = bool(w is not None and getattr(w, "operator_action_required", False)
                       and str(getattr(w, "operator_action_message", "")) == str(text))
        self._alert_add("action" if waiting else "notice", text, source=state_label(state_name))
        self._send_remote_alert(f"{state_label(state_name)}: {text}", key=f"banner:{text[:50]}")

    def _on_operator_notice(self, state_name, text):
        self._alert_add("notice", text, source=state_label(state_name))
        self._send_remote_alert(f"{state_label(state_name)}: {text}", key=f"banner:{text[:50]}")

    def _send_remote_alert(self, text, key=None):
        """Forward to alerts.send_alert (no-op unless an endpoint is set in gui_settings.json 'alerts')."""
        try:
            import alerts
            alerts.send_alert(text, key=key)
        except Exception as e:
            print(f"[alerts] not sent: {e}")

    def _check_telemetry_watchdog(self):
        """
        Telemetry watchdog (P1-4): the state thread updates world.last_update_time_s on every telemetry
        tick. If that stops for > 60 s (hung serial read, deadlocked procedure) or the FAA / Kepco
        readings are NaN for > 5 min, show a banner and send an alert. Runs on a GUI timer, so it still
        works when the state thread is stuck.
        """
        now = time.time()
        last = getattr(self.world, "last_update_time_s", None)
        stale_s = (now - last) if last else 0.0
        if stale_s > 300 and os.environ.get("PAC2_SUPERVISED") == "1" and not getattr(self, "_watchdog_exiting", False):
            # Supervised (scripts/run_supervised.sh): a hang while idle or regulating is fixed by a restart (the
            # LS370 keeps regulating; the new instance re-adopts). During a cycle/ramp only warn: a restart
            # would stop the ramp from advancing, which the operator must decide.
            dt = getattr(self, "data_thread", None)
            st_name = dt.state.name() if (dt and dt.state) else IDLE_STATE
            if st_name in (IDLE_STATE, "regulate_temperature"):
                self._watchdog_exiting = True
                print(f"[WATCHDOG] telemetry stalled {stale_s:.0f} s in {st_name}; exiting for a supervised restart. Thread dump:")
                try:
                    import faulthandler
                    faulthandler.dump_traceback(all_threads=True)
                except Exception:
                    pass
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(75)
        if stale_s > 60:
            if not getattr(self, "_watchdog_stale_flag", False):
                self._watchdog_stale_flag = True
                msg = f"⚠️ Telemetry stalled: no instrument update for {stale_s:.0f} s (state: {getattr(self.world, 'current_phase', '?')}). The procedure may be hung on a serial read."
                self.show_operator_banner(msg)
                self._send_remote_alert(msg, key="watchdog_stale")
        else:
            self._watchdog_stale_flag = False
        try:
            mr = _states_mod.most_recent_measurements()
            bad = [k for k in ("faa_temperature", "labjack_kepco_current") if k in mr and not np.isfinite(mr[k])]
        except Exception:
            bad = []
        if bad:
            self._watchdog_nan_since = getattr(self, "_watchdog_nan_since", None) or now
            if now - self._watchdog_nan_since > 300 and not getattr(self, "_watchdog_nan_flag", False):
                self._watchdog_nan_flag = True
                msg = f"⚠️ Telemetry: {', '.join(bad)} reading NaN for > 5 min. Check the instrument connection."
                self.show_operator_banner(msg)
                self._send_remote_alert(msg, key="watchdog_nan")
        else:
            self._watchdog_nan_since = None
            self._watchdog_nan_flag = False
        self._check_ls370_loop_registers(now)
        actions, _ = self._alert_state()
        if actions and not getattr(self.world, "operator_action_required", False):
            self._clear_alert_actions()

    def _check_ls370_loop_registers(self, now):
        """
        Every 30 s read the LS370 loop registers on a worker thread (rc.loop_status()). If the PID is driving the
        output while CMODE?/HTRRNG? (= the front panel) say otherwise, banner + alert once. That state came from the
        old Stop button writing CMODE 4, which blanks the front panel without stopping the output.
        """
        st = getattr(self, "_ls370_loop", None)
        if st and st.get("stale"):
            if not getattr(self, "_ls370_stale_flag", False):
                self._ls370_stale_flag = True
                dt = getattr(self, "data_thread", None)
                is_reg = bool(dt and dt.state and dt.state.name() == "regulate_temperature")
                msg = (f"⚠️ LS370 front panel says mode {st.get('mode')}, range {st.get('range')}, but its PID is driving the "
                       f"output ({st.get('htr', float('nan')):.1f} %). "
                       + ("Regulation re-writes the registers within 5 min." if is_reg else
                          "Press Regulate: it adopts the running loop and fixes the front panel without disturbing it."))
                self.show_operator_banner(msg)
                self._send_remote_alert(msg, key="ls370_stale_regs")
        else:
            self._ls370_stale_flag = False
        if now - getattr(self, "_ls370_loop_t", 0.0) < 30 or getattr(self, "_ls370_poll_busy", False):
            return
        rc = getattr(getattr(getattr(self.world, "station", None), "ls370", None), "heater", None)
        if rc is None or not hasattr(rc, "loop_status"):
            return
        self._ls370_loop_t = now
        self._ls370_poll_busy = True

        def _poll():
            try:
                self._ls370_loop = dict(rc.loop_status(), t=time.time())
            except Exception as e:
                print(f"[LS370] loop status poll failed: {e}")
            finally:
                self._ls370_poll_busy = False
        threading.Thread(target=_poll, daemon=True).start()

    def _on_procedure_finished(self, state_name):
        self._set_status_badge("IDLE", "idle")
        idx = self.combo_box.findData(IDLE_STATE)
        if idx >= 0:
            self.combo_box.blockSignals(True)
            self.combo_box.setCurrentIndex(idx)
            self.combo_box.blockSignals(False)
        self.lbl_script_name.setText(f"Active Script: {state_label(IDLE_STATE)}")

    def _on_procedure_error(self, state_name, err_msg):
        self._set_status_badge("ERROR", "error")
        idx = self.combo_box.findData(IDLE_STATE)
        if idx >= 0:
            self.combo_box.blockSignals(True)
            self.combo_box.setCurrentIndex(idx)
            self.combo_box.blockSignals(False)
        self.lbl_script_name.setText(f"Active Script: {state_label(IDLE_STATE)}")
        mag_I = abs(getattr(self, "_latest_magnet_current", 0.0))
        if mag_I > _states_mod.MAGNET_ENERGIZED_A:
            self.show_operator_banner(
                f"⚠️ Error in {state_label(state_name)}: {err_msg}. "
                f"WARNING: Magnet current is held at {mag_I:.3f} A! Run 'Ramp Down Magnet' to de-energize safely."
            )
        else:
            self.show_operator_banner(f"⚠️ Error in {state_label(state_name)}: {err_msg}. Reverted safely to Idle.")
        self._send_remote_alert(f"ERROR in {state_label(state_name)}: {err_msg} (magnet {mag_I:.3f} A). Now Idle.", key=f"error:{state_name}")


    def _compute_faa_window_rms_uk(self):
        """Compute FAA temperature RMS (standard deviation around mean, in uK) for the currently displayed time window."""
        dataset = self.historical_dataset if self.displaying_historical else self.live_dataset
        if dataset is None or not hasattr(dataset, "cache"):
            return None
        try:
            data = dataset.cache.data()
            if not data or "time" not in data or "time" not in data["time"]:
                return None
            t = data["time"]["time"]
            if len(t) < 2:
                return None

            faa_arr = None
            for k in ("faa_temperature", "faa"):
                if k in data and k in data[k] and len(data[k][k]) > 0:
                    faa_arr = data[k][k]
                    break
            if faa_arr is None or len(faa_arr) < 2:
                return None

            n = min(len(t), len(faa_arr))
            t = np.asarray(t[:n], dtype=float)
            faa_arr = np.asarray(faa_arr[:n], dtype=float)

            x0, x1 = None, None
            if self.user_has_zoomed and self.axes_list:
                try:
                    xlim = self.axes_list[0].get_xlim()
                    if xlim[0] < xlim[1]:
                        x0, x1 = float(xlim[0]), float(xlim[1])
                except Exception:
                    pass

            if x0 is None or x1 is None:
                tw_str = str(self.time_window or "6 Hours").lower()
                if self.displaying_historical or "all" in tw_str:
                    x0, x1 = float(t[0]), float(t[-1])
                else:
                    if "15" in tw_str or "min" in tw_str:
                        window_s = 900.0
                    elif "month" in tw_str or "30" in tw_str:
                        window_s = 30.0 * 86400.0
                    elif "week" in tw_str or "7" in tw_str:
                        window_s = 7.0 * 86400.0
                    elif "day" in tw_str or "24" in tw_str:
                        window_s = 86400.0
                    elif "1" in tw_str and "hour" in tw_str:
                        window_s = 3600.0
                    elif "6" in tw_str and "hour" in tw_str:
                        window_s = 21600.0
                    else:
                        window_s = 21600.0
                    x1 = float(t[-1])
                    x0 = x1 - window_s

            i0 = int(np.searchsorted(t, x0, side="left"))
            i1 = int(np.searchsorted(t, x1, side="right"))
            if i1 - i0 < 2:
                return None

            sub = faa_arr[i0:i1]
            valid = sub[np.isfinite(sub) & (sub > 0)]
            if len(valid) < 2:
                return None

            return float(np.std(valid)) * 1e6
        except Exception:
            return None

    def _update_faa_card_rms_title(self, control_engaged=None):
        """Update the FAA STAGE metric card title with (xx.x uK rms) when control is engaged."""
        if "faa_temperature" not in self.metric_tiles:
            return
        faa_spec = self.metric_tiles["faa_temperature"]
        if control_engaged is None:
            control_engaged = getattr(self, "_last_control_engaged", False)
        else:
            self._last_control_engaged = bool(control_engaged)

        if control_engaged:
            rms_uk = self._compute_faa_window_rms_uk()
            if rms_uk is not None and np.isfinite(rms_uk):
                faa_spec["lbl_t"].setText(f"FAA STAGE ({rms_uk:.1f} uK rms)")
                return
        faa_spec["lbl_t"].setText("FAA STAGE")

    # ------------- Dual-Row Status Bar ---------------
    def _format_val(self, key, val, units):
        alias = display_name(key)
        unit = units.get(key, "")
        if isinstance(val, (int, float)):
            if np.isnan(val):
                return f"{alias}: NaN"
            if plot_utils.overrange(key, val):
                return f"{alias}: OVERRANGE"
            if "vac" in key.lower() or "torr" in str(unit).lower() or "torr" in key.lower():
                if val < 0.1:
                    return f"{alias}: {val*1000.0:.2f} mTorr"
                elif val < 10.0:
                    return f"{alias}: {val:.3f} Torr"
                else:
                    return f"{alias}: {val:.2f} Torr"
            if "temp" in key.lower() or str(unit).upper() == "K":
                return f"{alias}: {format_cryo_temp(val)}"
            if "current" in key.lower() or str(unit).upper() == "A":
                return f"{alias}: {format_magnet_current(val)}"
            return f"{alias}: {val:.3f} {unit}".strip()
        return f"{alias}: {val}"

    def _update_latest_status(self, data_mr, units, keys):
        if not data_mr:
            self.lbl_latest_vals.setText("LATEST  Waiting for telemetry...")
            return

        is_light = (self.theme == "light")
        key_fallbacks = {
            "cryocon_chB_temperature": ["cryocon_chB_temperature", "chB_temperature", "chB", "charcoal"],
            "cryocon_chC_temperature": ["cryocon_chC_temperature", "chC_temperature", "chC", "4k_flange", "4k"],
            "cryocon_chD_temperature": ["cryocon_chD_temperature", "chD_temperature", "chD", "pot"],
            "cryocon_chA_temperature": ["cryocon_chA_temperature", "chA_temperature", "chA", "60k_flange", "60k", "40k_flange", "40k"],
            "faa_temperature": ["faa_temperature", "faa"],
            "labjack_he3_pressure": ["labjack_he3_pressure", "he3_pressure"],
            "labjack_kepco_current": ["labjack_kepco_current", "kepco_current"],
        }
        for key, spec in self.metric_tiles.items():
            if key == "relay_heater_status":
                continue
            raw_val = None
            for candidate in key_fallbacks.get(key, [key]):
                if candidate in data_mr:
                    raw_val = data_mr[candidate]
                    break
            if raw_val is not None:
                val = float(raw_val) if isinstance(raw_val, (int, float)) and np.isfinite(raw_val) else None

                if plot_utils.overrange(key, val):
                    spec["val"].setText(f"OVERRANGE (> {plot_utils.DISPLAY_MAX_K[key]:g} K)")
                elif key in ("faa_temperature", "cryocon_chD_temperature", "cryocon_chC_temperature",
                             "cryocon_chB_temperature", "cryocon_chA_temperature"):
                    if val is not None:
                        spec["val"].setText(format_cryo_temp(val))
                    else:
                        spec["val"].setText("NaN")
                elif key == "labjack_he3_pressure":
                    if val is not None:
                        spec["val"].setText(f"{val:.2f} bar")
                    else:
                        spec["val"].setText("—")
                elif key == "labjack_kepco_current":
                    if val is not None:
                        spec["val"].setText(format_magnet_current(val))
                        self._latest_magnet_current = val
                    else:
                        spec["val"].setText("0.0 mA")
                        self._latest_magnet_current = 0.0

                # Visual watchdogs and solid theme styling
                acc = spec["accent"]
                card_style = None
                val_style = None

                if key == "labjack_he3_pressure" and val is not None and val > 9.5:
                    card_style = "QFrame#metric_tile { background-color: #991b1b; border: 2px solid #ef4444; border-radius: 6px; }"
                    val_style = "color: #ffffff; font-weight: 800; font-size: 18px; background: transparent;"
                elif key == "labjack_he3_pressure" and val is not None and val > 9.0:
                    card_style = "QFrame#metric_tile { background-color: #b45309; border: 2px solid #f59e0b; border-radius: 6px; }"
                    val_style = "color: #ffffff; font-weight: 800; font-size: 18px; background: transparent;"
                elif key == "labjack_kepco_current" and val is not None and abs(val) > 0.5:
                    card_style = f"QFrame#metric_tile {{ background-color: {acc}; border: 2px solid #38bdf8; border-radius: 6px; }}"
                    val_style = "color: #ffffff; font-weight: 800; font-size: 18px; background: transparent;"
                else:
                    card_style = f"QFrame#metric_tile {{ background-color: {acc}; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.18); }}"
                    val_style = "color: #ffffff; font-weight: 800; font-size: 18px; background: transparent;"

                if card_style:
                    spec["card"].setStyleSheet(card_style)
                if val_style:
                    spec["val"].setStyleSheet(val_style)
                if "lbl_t" in spec:
                    spec["lbl_t"].setStyleSheet("color: rgba(255, 255, 255, 0.92); font-weight: 700; font-size: 11px; background: transparent;")

        # Update Grey Relay State & Heater Status Card
        if "relay_heater_status" in self.metric_tiles:
            spec = self.metric_tiles["relay_heater_status"]
            rel_val = None
            if hasattr(self.world, "station") and hasattr(self.world.station, "labjack") and self.world.station.labjack:
                try:
                    rel_val = self.world.station.labjack.relay.cache.get()
                except Exception:
                    pass
            if not rel_val or rel_val == "UNKNOWN":
                rel_val = data_mr.get("labjack_relay")
            if not rel_val or rel_val == "UNKNOWN":
                rel_val = "CONTROL"
            rel_str = str(rel_val).upper()

            htr_pct = 0.0
            if "ls370_heater_out" in data_mr and data_mr["ls370_heater_out"] is not None:
                try:
                    htr_pct = float(data_mr["ls370_heater_out"])
                except Exception:
                    pass

            rc = None
            if hasattr(self.world, "station") and hasattr(self.world.station, "ls370") and self.world.station.ls370:
                rc = getattr(self.world.station.ls370, "heater", None)

            mode_name = "Closed loop" if rel_str == "CONTROL" else "Open loop"
            sp_disp = None
            loop_stale = False
            if rc:
                try:
                    # Show what the LS370 itself reports (= its front panel), polled every 30 s.
                    lst = getattr(self, "_ls370_loop", None)
                    if lst and time.time() - lst.get("t", 0) < 120:
                        m, r = str(lst.get("mode", "")), str(lst.get("range", ""))
                        loop_stale = bool(lst.get("stale"))
                    else:
                        m = str(getattr(rc, "commanded_mode", None) or "").lower()
                        r = str(getattr(rc, "commanded_range", None) or "").lower()
                    sp = rc.setpoint.cache.get()
                    if loop_stale:
                        mode_name = "PID running, LS370 panel says OFF"
                    elif r == "off":
                        mode_name = "OFF"
                    elif "closed" in m:
                        mode_name = "Closed loop"
                    elif "open" in m:
                        mode_name = "Open loop"
                    if sp is not None:
                        sp_k = float(sp)
                        sp_disp = f"{sp_k*1000.0:.1f} mK" if sp_k < 1.0 else f"{sp_k:.3f} K"
                except Exception:
                    pass

            spec["lbl_t"].setText(f"RELAY STATE: {rel_str}")
            sp_txt = f", SP {sp_disp}" if (sp_disp and mode_name.startswith(("Closed loop", "PID running"))) else ""
            spec["val"].setText(f"output {htr_pct:.2f}% ({mode_name}{sp_txt})")
            card_bg = "#b91c1c" if loop_stale else "#475569"
            card_style = f"QFrame#metric_tile {{ background-color: {card_bg}; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.18); }}"
            val_style = "color: #ffffff; font-weight: 700; font-size: 12px; background: transparent;"
            spec["card"].setStyleSheet(card_style)
            spec["val"].setStyleSheet(val_style)
            spec["lbl_t"].setStyleSheet("color: rgba(255, 255, 255, 0.92); font-weight: 700; font-size: 11px; background: transparent;")
            if hasattr(self, "lbl_relay_mode_status"):
                self.lbl_relay_mode_status.setText(f"State: {rel_str}")

            dt = getattr(self, "data_thread", None)
            is_reg_state = bool(dt and getattr(dt, "state", None) and dt.state.name() == "regulate_temperature")
            control_engaged = (rel_str == "CONTROL") and (is_reg_state or mode_name == "Closed loop" or htr_pct > 0.0)
            self._update_faa_card_rms_title(control_engaged=control_engaged)

        shown_keys = [k for k in PRIMARY_STATUS_KEYS if k in data_mr]
        other_keys = [k for k in keys if k in data_mr and k not in PRIMARY_STATUS_KEYS and k not in ("time", "elapsed_time")]
        all_status_keys = shown_keys + other_keys[:3]

        parts = [self._format_val(k, data_mr[k], units) for k in all_status_keys]
        self.lbl_latest_vals.setText("LATEST   " + "   │   ".join(parts))

    def _update_cursor_status(self):
        event = self.on_mouse_move_event
        if event is None or not event.inaxes or event.xdata is None:
            self.lbl_cursor_vals.setText("CURSOR  [Hover over plot to inspect point]")
            return

        dataset = self.historical_dataset if self.displaying_historical else self.live_dataset
        if dataset is None:
            return

        try:
            data = dataset.cache.data()
            if not data or "time" not in data or "time" not in data["time"]:
                return
            t = data["time"]["time"]
            if len(t) == 0:
                return
            # Fast O(log N) binary search with zero array allocations
            xloc_ind = int(np.searchsorted(t, event.xdata))
            if xloc_ind >= len(t):
                xloc_ind = len(t) - 1
            elif xloc_ind > 0 and abs(t[xloc_ind - 1] - event.xdata) < abs(t[xloc_ind] - event.xdata):
                xloc_ind = xloc_ind - 1

            from plot_utils import get_dataset_units, epoch_to_local_str
            units = get_dataset_units(dataset)

            shown_keys = [k for k in PRIMARY_STATUS_KEYS if k in data]
            other_keys = [k for k in data.keys() if k not in PRIMARY_STATUS_KEYS and k not in ("time", "elapsed_time")]
            all_status_keys = shown_keys + other_keys[:3]

            parts = []
            t_str = epoch_to_local_str(t[xloc_ind], include_seconds=True)
            parts.append(f"t={t_str}")
            for key in all_status_keys:
                if key in data and key in data[key] and len(data[key][key]) > xloc_ind:
                    val = data[key][key][xloc_ind]
                    parts.append(self._format_val(key, val, units))
            self.lbl_cursor_vals.setText("CURSOR   " + "   │   ".join(parts))
        except Exception:
            pass

    # ---------------- restart handling (robust daily use) ----------------
    def _previous_instance_state(self):
        """
        (state, unix_time) of the last state.log entry written BEFORE this process started, i.e. what the
        previous GUI instance was doing when it stopped. None if unknown.
        """
        start = float(os.environ.get("PAC2_START_TIME", "0") or 0) or time.time()
        base = Path.home() / "2pac_logs"
        days = sorted((d for d in base.glob("20??-??-??") if (d / "state.log").exists()), reverse=True)[:2]
        for d in days:
            try:
                with open(d / "state.log", "rb") as fh:
                    fh.seek(0, 2)
                    size = fh.tell()
                    fh.seek(max(0, size - 262144))
                    tail = fh.read().decode("utf-8", "replace").splitlines()
            except Exception:
                continue
            for line in reversed(tail):
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                try:
                    t = float(parts[0])
                except ValueError:
                    continue
                if t < start - 1.0:
                    return parts[2].strip(), t
        return None

    def _startup_resume_check(self):
        """
        Called once shortly after startup. If the previous instance was regulating and the LS370 loop is still
        running with the relay in CONTROL, re-adopt it (regulate_temperature writes nothing to a healthy loop).
        If it was in any other procedure, do NOT resume: tell the operator what was running.
        """
        prev = self._previous_instance_state()
        if not prev:
            return
        state_name, t_prev = prev
        when = datetime.fromtimestamp(t_prev).strftime("%Y-%m-%d %H:%M")
        dt = getattr(self, "data_thread", None)
        cur = dt.state.name() if (dt and dt.state) else IDLE_STATE
        if cur != IDLE_STATE or state_name == IDLE_STATE:
            return
        if state_name == "regulate_temperature":
            rc = getattr(getattr(getattr(self.world, "station", None), "ls370", None), "heater", None)
            relay = self._cached_relay_state() if hasattr(self, "_cached_relay_state") else None

            def _probe():
                try:
                    st = rc.loop_status() if rc is not None else {}
                except Exception as e:
                    print(f"[RESUME] LS370 loop status failed: {e}")
                    st = {}
                if relay == "CONTROL" and st.get("closed_loop"):
                    print(f"[RESUME] previous instance was regulating (last seen {when}); re-adopting the running loop.")
                    self.sig_resume_regulation.emit()
                else:
                    self.sig_operator_banner.emit(
                        f"ℹ️ The GUI restarted. It was regulating until {when}, but the LS370 loop is not running "
                        f"(relay {relay}, loop {st.get('mode', '?')}). Regulation was NOT restarted automatically.")
            threading.Thread(target=_probe, daemon=True).start()
            return
        if time.time() - t_prev > 24 * 3600:
            return
        mag_I = getattr(self, "_latest_magnet_current", float("nan"))
        msg = (f"⚠️ The GUI restarted while '{state_label(state_name)}' was running (last seen {when}). "
               f"Procedures do not resume automatically. Magnet current now {mag_I:.3f} A. Check the cryostat, then "
               "resume (e.g. He-3 + ADR: Resume at Magnet Ramp) or Ramp Down Magnet.")
        self.show_operator_banner(msg)
        self._send_remote_alert(msg, key="restart_mid_procedure")

