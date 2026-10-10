# 2PAC Legacy / Archive Code (`older/`)

This directory archives historical code and prototypes from earlier development iterations of the 2PAC ADR control system. These files are preserved for historical reference and algorithm inspection, but are not part of the active production application.

## Archived Files

| File | Historical Purpose | Active Replacement |
|---|---|---|
| `2pacgui_qt.py` | Original monolithic PyQt GUI | `gui.py` + `plot_utils.py` |
| `log_data.py` | Original text-based CSV/dat logging script | `daily_logger.py` (Daily partitioned SQLite) |
| `read_logs.py` | Original offline text log parser and viewer | `daily_logger.py` + GUI History tab |
| `world_no_mpl.py` | Headless console runner without matplotlib | `world.py` + `main.py` |
| `guitodo.txt` | Initial developer notes and feature roadmap | Modern GUI implementation and `docs/` |

> [!NOTE]
> The active production application is launched via `./launch_gui.sh` or `python main.py`.
