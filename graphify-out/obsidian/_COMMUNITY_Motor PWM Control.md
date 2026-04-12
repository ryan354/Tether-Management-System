---
type: community
cohesion: 0.11
members: 21
---

# Motor PWM Control

**Cohesion:** 0.11 - loosely connected
**Members:** 21 nodes

## Members
- [[.__init__()_1]] - code - app\main.py
- [[._compute_rc_pwm()]] - code - app\main.py
- [[._invert_pwm()]] - code - app\main.py
- [[._ramp()]] - code - app\main.py
- [[.set_desired()]] - code - app\main.py
- [[.set_pid_config()]] - code - app\main.py
- [[.stop()_1]] - code - app\main.py
- [[.update()]] - code - app\main.py
- [[Invert PWM around neutral (1000). 850-1150, 1150-850, etc.]] - rationale - app\main.py
- [[Legacy alias - use set_controller_config instead.]] - rationale - app\main.py
- [[Motor]] - code - app\main.py
- [[Step current toward target by at most acceldecel_rate per cycle.]] - rationale - app\main.py
- [[Stop motor - set PWM to neutral and reset ramp state.]] - rationale - app\main.py
- [[Trapezoidal + FF+P controller - RC PWM (700-1300).          Stage 1 - Length]] - rationale - app\main.py
- [[Update motor state with encoder feedback and compute PWM.]] - rationale - app\main.py
- [[Update motor with encoder feedback (cable length in meters, speed in ms)]] - rationale - app\main.py
- [[enable_pwm()]] - code - app\main.py
- [[get_all_motors_status()]] - code - app\main.py
- [[load_config()]] - code - app\main.py
- [[set_motor()]] - code - app\main.py
- [[update_encoder()]] - code - app\main.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Motor_PWM_Control
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_FastAPI Core & Config]]
- 3 edges to [[_COMMUNITY_USBL Fold Mechanism]]

## Top bridge nodes
- [[.update()]] - degree 10, connects to 2 communities
- [[get_all_motors_status()]] - degree 3, connects to 2 communities
- [[Motor]] - degree 10, connects to 1 community
- [[.stop()_1]] - degree 4, connects to 1 community
- [[enable_pwm()]] - degree 3, connects to 1 community