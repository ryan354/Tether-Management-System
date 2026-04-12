---
type: community
cohesion: 0.12
members: 24
---

# USBL Fold Mechanism

**Cohesion:** 0.12 - loosely connected
**Members:** 24 nodes

## Members
- [[.__init__()_2]] - code - app\main.py
- [[._load_config()]] - code - app\main.py
- [[._on_fold_limit()]] - code - app\main.py
- [[._on_unfold_limit()]] - code - app\main.py
- [[._stop_motor()]] - code - app\main.py
- [[.check_safety_timeout()]] - code - app\main.py
- [[.fold()]] - code - app\main.py
- [[.get_status()_1]] - code - app\main.py
- [[.stop()_2]] - code - app\main.py
- [[.unfold()]] - code - app\main.py
- [[Emergency stop the fold motor.]] - rationale - app\main.py
- [[FoldMotor]] - code - app\main.py
- [[Get fold mechanism status.]] - rationale - app\main.py
- [[Load fold motor PWM settings from CONFIG.]] - rationale - app\main.py
- [[Set PWM value for channel (0-4095)]] - rationale - app\main.py
- [[Set direct PWM value (700-1300). Set to -1 to disable direct mode.]] - rationale - app\main.py
- [[Simple motor controller for foldunfold mechanism with limit switches.]] - rationale - app\main.py
- [[Unfold the USBL mount.]] - rationale - app\main.py
- [[fold_mount()]] - code - app\main.py
- [[get_fold_status()]] - code - app\main.py
- [[set_direct_pwm()]] - code - app\main.py
- [[set_pwm()]] - code - app\main.py
- [[stop_fold()]] - code - app\main.py
- [[unfold_mount()]] - code - app\main.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/USBL_Fold_Mechanism
SORT file.name ASC
```

## Connections to other communities
- 10 edges to [[_COMMUNITY_FastAPI Core & Config]]
- 3 edges to [[_COMMUNITY_Motor PWM Control]]

## Top bridge nodes
- [[set_pwm()]] - degree 8, connects to 2 communities
- [[FoldMotor]] - degree 12, connects to 1 community
- [[.stop()_2]] - degree 6, connects to 1 community
- [[.get_status()_1]] - degree 5, connects to 1 community
- [[._load_config()]] - degree 4, connects to 1 community