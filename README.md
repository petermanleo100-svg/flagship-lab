# Flagship Lab

å››ä¸ªé¢å‘å››å¤§å®žä¹ å²—ä½çš„å¯å®¡è®¡è½¯ä»¶å·¥ç¨‹é¡¹ç›®ã€‚ç¬¬äºŒé˜¶æ®µå·²è¦†ç›– FastAPI/OpenAPIã€JWTè§’è‰²æƒé™ã€ç‰ˆæœ¬åŒ–è§„åˆ™DSLã€å¯éªŒè¯è¯æ®åŒ…ã€æ··åˆæ£€ç´¢ã€æ—¶é—´åˆ‡åˆ†é£Žé™©æ¨¡åž‹å’Œå¯é‡æ”¾æŽ§åˆ¶äº‹ä»¶æµã€‚

## å½“å‰å¯è¿è¡Œæ¨¡å—

- **TaxFlow Nexus**ï¼šåˆæˆå‘ç¥¨ç”Ÿæˆã€æ‰¹é‡å…¥åº“ã€ç‰ˆæœ¬åŒ–ç¨ŽåŠ¡è§„åˆ™ã€å¼‚å¸¸å‘çŽ°ã€å“ˆå¸Œå®¡è®¡é“¾ã€‚
- **RegIntel Copilot**ï¼šæ³•è§„æ–‡æ¡£ç‰ˆæœ¬åŒ–ã€ä¸­æ–‡/è‹±æ–‡è¯é¡¹æ£€ç´¢ã€å¸¦åŽŸæ–‡å¼•ç”¨çš„è¯æ®åž‹å›žç­”ã€æ— è¯æ®æ‹’ç­”ã€‚
- **ControlPulse**ï¼šITæŽ§åˆ¶äº‹ä»¶æŽ¥å…¥ã€ç­–ç•¥å³ä»£ç æ£€æµ‹ã€æŽ§åˆ¶ç¼ºé™·æ¡ˆä»¶ã€è¯æ®å“ˆå¸Œã€‚
- **RiskGraph Investigator**ï¼šä¼ä¸š/è´¦æˆ·äº¤æ˜“å›¾ã€å…±äº«è´¦æˆ·ä¸Žå¾ªçŽ¯äº¤æ˜“æ£€æµ‹ã€å¯è§£é‡Šé£Žé™©è¯„åˆ†ã€‚

æ–°å¢žå¯æ ¸éªŒèƒ½åŠ›ï¼š

- RegIntelï¼šè¯é¡¹åˆ†æ•°ä¸Žå­—ç¬¦TF-IDFæ··åˆæŽ’åºï¼Œå›ºå®šè¯„æµ‹é›†è¾“å‡ºRecall@Kå’ŒMRRã€‚
- RiskGraphï¼šNetworkXå›¾ç‰¹å¾ã€ä¸¥æ ¼æœˆä»½åˆ‡åˆ†ã€éšæœºæ£®æž—åŸºçº¿ã€æ¨¡åž‹å¡å’Œæ¨¡åž‹åˆ¶å“ã€‚
- ControlPulseï¼šJSONLè¿½åŠ å¼äº‹ä»¶æµã€åç§»é‡ã€æµå“ˆå¸Œé“¾ã€æ£€æŸ¥ç‚¹ã€å¹‚ç­‰æ¶ˆè´¹å’Œå›žæ”¾ã€‚

## å¿«é€Ÿå¼€å§‹

```powershell
$env:PYTHONPATH="src"
python -m flagship_lab.cli demo --db work/demo.db
python -m unittest discover -s tests -v
python -m flagship_lab.cli serve --db work/server.db --port 8080
```

ç¬¬äºŒé˜¶æ®µ FastAPIï¼š

```powershell
python -m pip install -e ".[test]"
$env:FLAGSHIP_JWT_SECRET="replace-with-a-random-secret-of-at-least-32-characters"
python -m flagship_lab.cli api --db work/api.db --port 8000 --allow-dev-tokens
```

æµè§ˆ `http://127.0.0.1:8000/docs` æŸ¥çœ‹ OpenAPI äº¤äº’æ–‡æ¡£ã€‚`--allow-dev-tokens` ä»…ä¾›æœ¬åœ°æ¼”ç¤ºï¼›é»˜è®¤å…³é—­ã€‚

ç”Ÿæˆæ›´å¤§è§„æ¨¡çš„ TaxFlow åŸºå‡†æ•°æ®ï¼š

```powershell
$env:PYTHONPATH="src"
python -m flagship_lab.cli benchmark --db work/benchmark.db --rows 100000
python -m flagship_lab.cli reg-eval --db work/reg-eval.db --k 3
python -m flagship_lab.cli risk-benchmark --entities 400 --months 12 --train-through 8 --output-dir artifacts/risk-model
python -m flagship_lab.cli control-stream-demo --db work/control.db --stream work/events.jsonl --checkpoint work/checkpoint.json
```

æœåŠ¡å¯åŠ¨åŽå¯è®¿é—® `GET /health`ã€`POST /tax/transactions`ã€`POST /tax/runs`ã€`GET /tax/findings?run_id=...`ã€`POST /reg/documents`ã€`POST /reg/answer`ã€`POST /controls/events`ã€`GET /controls/cases`ã€`POST /graph/entities`ã€`POST /graph/edges`ã€`GET /graph/findings` å’Œ `GET /audit/verify`ã€‚

## çœŸå®žæ€§è§„åˆ™

README ä¸Žç®€åŽ†ä¸­çš„æ€§èƒ½ã€å¬å›žçŽ‡ç­‰æ•°å­—å¿…é¡»æ¥è‡ª `benchmark` æˆ–æµ‹è¯•è¾“å‡ºã€‚ä¸åº”æŠŠæœªæ¥è§„åˆ’å½“æˆå·²å®žçŽ°åŠŸèƒ½ã€‚

ç¬¬äºŒé˜¶æ®µ DSL å®žæµ‹ï¼š10ä¸‡æ¡åˆæˆäº¤æ˜“ç«¯åˆ°ç«¯åžå `43,324.53 æ¡/ç§’`ï¼›è¯¦ç»†çŽ¯å¢ƒé™åˆ¶è§ [`docs/benchmark-2026-08-11-phase2.md`](docs/benchmark-2026-08-11-phase2.md)ã€‚æž¶æž„è¾¹ç•Œè§ [`docs/architecture.md`](docs/architecture.md)ï¼Œæ¼”ç¤ºæ­¥éª¤è§ [`docs/demo-guide.md`](docs/demo-guide.md)ã€‚

## å·²å®Œæˆçš„ç¬¬äºŒé˜¶æ®µèƒ½åŠ›

1. FastAPI/OpenAPI å’Œ Pydantic è¾“å…¥æ ¡éªŒã€‚
2. HS256 JWTï¼ŒåŒ…å« `viewer`ã€`analyst`ã€`reviewer`ã€`admin` å››ç±»è§’è‰²ã€‚
3. ç¨ŽåŠ¡è§„åˆ™ JSON DSLã€è§„åˆ™åŒ…ç‰ˆæœ¬ä¸Žå†…å®¹å“ˆå¸Œã€‚
4. TaxFlow è¯æ® ZIPï¼šè¿è¡Œã€å‘çŽ°ã€å®¡è®¡äº‹ä»¶å’Œ SHA-256 æ¸…å•ï¼›æ”¯æŒç¯¡æ”¹æ£€æµ‹ã€‚
5. 16é¡¹è‡ªåŠ¨åŒ–æµ‹è¯•ï¼Œè¦†ç›–401/403ã€è§„åˆ™åŒ…æ ¡éªŒã€è¯æ®ä¸‹è½½æƒé™ã€äº‹ä»¶æµã€ç¯¡æ”¹æ£€æµ‹å’Œæ•°æ®åº“è¿ç§»å¾€è¿”ã€‚
6. RegIntelæ··åˆæ£€ç´¢è¯„æµ‹ã€RiskGraphæ—¶é—´åˆ‡åˆ†æ¨¡åž‹å’ŒControlPulseäº‹ä»¶æµå›žæ”¾ã€‚

## ä¸‹ä¸€é˜¶æ®µ

1. å¢žåŠ åˆ·æ–°ä»¤ç‰Œã€å¯†é’¥è½®æ¢ã€ç”¨æˆ·ç›®å½•å’Œæ›´ç»†ç²’åº¦èµ„æºæƒé™ã€‚
2. TaxFlow å¢žåŠ å­—æ®µçº§è¡€ç¼˜ã€å¼‚å¸¸å®¡æ‰¹æµå’Œè¯æ®åŒ…éžå¯¹ç§°ç­¾åã€‚
3. RegIntelå°†å½“å‰è¯é¡¹+å­—ç¬¦TF-IDFå‡çº§ä¸ºBM25+embedding+rereankerï¼Œå¹¶æ‰©å±•å…¬å¼€æ•°æ®è¯„æµ‹é›†ã€‚
4. ControlPulseå°†JSONLé€‚é…å™¨å‡çº§ä¸ºRedpanda/Kafkaã€OPAå’Œå¯¹è±¡å­˜å‚¨è¯æ®æ¹–ã€‚
5. RiskGraphå¢žåŠ SHAPã€å®žä½“éš”ç¦»éªŒè¯å’ŒNeo4jé€‚é…ã€‚
6. å¢žåŠ  OpenTelemetry å¯è§‚æµ‹æ€§ï¼Œå¹¶æŠŠå½“å‰ React æ¼”ç¤ºç«¯æ‰©å±•ä¸ºå®Œæ•´ç®¡ç†å·¥ä½œå°ã€‚

## éƒ¨ç½²ä¸Žæ¼”ç¤ºè¯æ®

- Alembicé¦–ç‰ˆè¿ç§»å·²åœ¨SQLiteå’Œæœ¬æœºPostgreSQL 18.3å®Œæˆå‡çº§ã€é™çº§ã€å†å‡çº§éªŒè¯ã€‚
- React/Viteæ¼”ç¤ºç«¯å·²å®Œæˆç”Ÿäº§æž„å»ºä¸Žæµè§ˆå™¨æ£€æŸ¥ï¼›è¯¦è§[`docs/deployment-evidence-2026-08-11.md`](docs/deployment-evidence-2026-08-11.md)ã€‚
- åŸºå‡†ã€æ¨¡åž‹åˆ¶å“ã€æµ‹è¯•å’Œè¯šä¿¡è¡¨è¿°æ±‡æ€»è§[`docs/portfolio-evidence-index.md`](docs/portfolio-evidence-index.md)ã€‚

