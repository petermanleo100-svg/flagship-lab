import hashlib,json
from datetime import datetime,timedelta,timezone
from flagship_lab.admission import REQUIRED_CONTROLS,verify_admission
SHA="a"*40
def evidence(tmp_path):
 checked=datetime.now(timezone.utc).isoformat();controls={}
 for name in REQUIRED_CONTROLS:
  relative=f"evidence/{name}.json";target=tmp_path/relative;target.parent.mkdir(exist_ok=True);target.write_text(json.dumps({"control":name}),encoding="utf-8");controls[name]={"status":"passed","verifier":"control-owner@example.com","verified_at_utc":checked,"evidence_uri":f"s3://admission/{name}.json","evidence_file":relative,"evidence_sha256":hashlib.sha256(target.read_bytes()).hexdigest()}
 return {"schema_version":3,"project":"flagship-lab","release_sha":SHA,"environment":"customer-staging","deployed_by":"release-engineer@example.com","controls":controls}
def test_admission_accepts_complete_release_bound_evidence(tmp_path):
 path=tmp_path/"evidence.json";path.write_text(json.dumps(evidence(tmp_path)),encoding="utf-8");assert verify_admission(path,SHA)["valid"] is True
def test_admission_rejects_expired_evidence(tmp_path):
 data=evidence(tmp_path);data["controls"]["kms_object_lock"]["verified_at_utc"]=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat();path=tmp_path/"evidence.json";path.write_text(json.dumps(data),encoding="utf-8");result=verify_admission(path,SHA);assert result["valid"] is False and result["errors"]==["control kms_object_lock evidence is expired or future-dated"]
def test_admission_rejects_self_approval_and_age_bypass(tmp_path):
 data=evidence(tmp_path);data["controls"]["otlp_trace_delivery"]["verifier"]="Release-Engineer@example.com";path=tmp_path/"evidence.json";path.write_text(json.dumps(data),encoding="utf-8");assert any("independent" in e for e in verify_admission(path,SHA)["errors"]);assert verify_admission(path,SHA,0)["valid"] is False
def test_admission_rejects_reused_evidence_file(tmp_path):
 data=evidence(tmp_path);data["controls"]["alert_delivery"]["evidence_file"]=data["controls"]["kafka_delivery_replay"]["evidence_file"];data["controls"]["alert_delivery"]["evidence_sha256"]=data["controls"]["kafka_delivery_replay"]["evidence_sha256"];path=tmp_path/"evidence.json";path.write_text(json.dumps(data),encoding="utf-8");assert any("must not be reused" in e for e in verify_admission(path,SHA)["errors"])
