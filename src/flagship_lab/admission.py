from __future__ import annotations
import json,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlparse
REQUIRED_CONTROLS={"alert_delivery","kafka_delivery_replay","kms_object_lock","managed_postgres_pitr_restore","oidc_key_rotation","otlp_trace_delivery","staging_migration_rollback"};_SHA=re.compile(r"^[0-9a-f]{40}$")
def verify_admission(path:str|Path,release_sha:str,max_age_hours:int=168)->dict:
 if not _SHA.fullmatch(release_sha):return {"valid":False,"errors":["release_sha must be a lowercase 40-character Git SHA"]}
 try:document=json.loads(Path(path).read_text(encoding="utf-8"))
 except (OSError,UnicodeError,json.JSONDecodeError) as exc:return {"valid":False,"errors":[f"cannot read admission evidence: {exc}"]}
 errors=[]
 if document.get("schema_version")!=1:errors.append("schema_version must be 1")
 if document.get("project")!="flagship-lab":errors.append("project must be flagship-lab")
 if document.get("release_sha")!=release_sha:errors.append("evidence release_sha does not match the requested release")
 if str(document.get("environment","")).lower() in {"","dev","development","local","test"}:errors.append("environment must identify a production-like deployment")
 controls=document.get("controls")
 if not isinstance(controls,dict):errors.append("controls must be an object");controls={}
 for name in sorted(REQUIRED_CONTROLS):
  item=controls.get(name)
  if not isinstance(item,dict):errors.append(f"missing required control: {name}");continue
  if item.get("status")!="passed":errors.append(f"control {name} is not passed")
  if not str(item.get("verifier","")).strip():errors.append(f"control {name} has no verifier")
  parsed=urlparse(str(item.get("evidence_uri","")))
  if parsed.scheme not in {"https","s3","gs","urn"} or (parsed.scheme in {"https","s3","gs"} and not parsed.netloc) or (parsed.scheme=="urn" and not parsed.path):errors.append(f"control {name} evidence_uri must be durable (https, s3, gs or urn)")
  try:
   checked=datetime.fromisoformat(str(item.get("verified_at_utc","")).replace("Z","+00:00"))
   if checked.tzinfo is None or checked.utcoffset()!=timedelta(0):raise ValueError
   age=datetime.now(timezone.utc)-checked.astimezone(timezone.utc)
   if age.total_seconds()<0 or age.total_seconds()>max_age_hours*3600:errors.append(f"control {name} evidence is expired or future-dated")
  except (TypeError,ValueError):errors.append(f"control {name} verified_at_utc is invalid")
 return {"valid":not errors,"project":"flagship-lab","release_sha":release_sha,"errors":errors}
