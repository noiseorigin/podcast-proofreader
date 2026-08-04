# config/by_ep —— 分期配置

按期号命名，`prepare` 会自动发现，不用写命令行参数。

| 文件 | 作用 | 与全局的关系 |
|---|---|---|
| `epXXX.corrections.json` | 本期纠错规则 | **叠加**在根目录 `corrections.json` 之上，同一个 `from` 时本期规则胜出 |
| `epXXX.speaker_map.json` | 本期发言人映射 | **替换**根目录 `speaker_map.json` |
| `epXXX.chapters.json` | 本期章节 | 仅在大纲**没有**「## 时间轴」节时启用 |

显式传 `--corrections` / `--speaker-map` / `--outline` 时，命令行参数完全接管，
本目录的同名文件不再参与。

## 格式

`epXXX.corrections.json`：

```json
[
  ["猪多多花园", "朱兜兜花园"],
  { "from": "龟背猪", "to": "龟背竹", "note": "植物名" }
]
```

`epXXX.speaker_map.json`：

```json
{ "发言人1": "主播甲", "发言人2": "嘉宾乙" }
```

`epXXX.chapters.json`：

```json
[
  ["00:00", "开场"],
  ["12:30", "主题讨论"]
]
```

## 短规则放这里，别放全局

全局纠错是精确字符串替换，没有词边界判断。2 字以内的规则会误伤正常词
（`花期→花旗` 会让「开花期」变成「开花旗」）。这类规则只放分期文件。
