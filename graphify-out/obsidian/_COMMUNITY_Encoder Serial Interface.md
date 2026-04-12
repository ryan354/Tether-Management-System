---
type: community
cohesion: 0.12
members: 24
---

# Encoder Serial Interface

**Cohesion:** 0.12 - loosely connected
**Members:** 24 nodes

## Members
- [[.__init__()]] - code - app\encoder.py
- [[._init_serial()]] - code - app\encoder.py
- [[._read_encoder()]] - code - app\encoder.py
- [[._read_loop()]] - code - app\encoder.py
- [[.add_encoder()]] - code - app\encoder.py
- [[.get_status()]] - code - app\encoder.py
- [[.get_status_dict()]] - code - app\encoder.py
- [[.reset_counter()]] - code - app\encoder.py
- [[.start()]] - code - app\encoder.py
- [[.stop()]] - code - app\encoder.py
- [[EncoderReader]] - code - app\encoder.py
- [[Get all encoder statuses]] - rationale - app\encoder.py
- [[Get named status dictionary]] - rationale - app\encoder.py
- [[Initialize serial connection]] - rationale - app\encoder.py
- [[Reset counter for specific encoder]] - rationale - app\encoder.py
- [[Start encoder reading thread]] - rationale - app\encoder.py
- [[Stop encoder reading thread]] - rationale - app\encoder.py
- [[Thread-safe encoder reader with Modbus RTU]] - rationale - app\encoder.py
- [[build_request()]] - code - app\encoder.py
- [[crc16()]] - code - app\encoder.py
- [[encoder.py]] - code - app\encoder.py
- [[get_encoder_reader()]] - code - app\encoder.py
- [[init_encoder()]] - code - app\encoder.py
- [[parse_response()]] - code - app\encoder.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Encoder_Serial_Interface
SORT file.name ASC
```
