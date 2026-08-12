import json
from datetime import datetime,timedelta,timezone
from flagship_lab.admission import REQUIRED_CONTROLS,verify_admission
SHA="a"*40
def evidence():
 checked=datetime.now(timezone.utc).isoformat();return {"schema_version":1,"project":"flagship-lab","release_sha":SHA,"environment":"customer-staging","controls":{name:{"status":"passed","verifier":"control-owner@example.com","verified_at_utc":checked,"evidence_uri":f"s3://admission/{name}.json"} for name in REQUIRED_CONTROLS}}
def test_admission_accepts_complete_release_bound_evidence(tmp_path):
 path=tmp_path/"evidence.json";path.write_text(json.dumps(evidence()),encoding="utf-8");assert verify_admission(path,SHA)["valid"] is True
def test_admission_rejects_expired_evidence(tmp_path):
 data=evidence();data["controls"]["kms_object_lock"]["verified_at_utc"]=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat();path=tmp_path/"evidence.json";path.write_text(json.dumps(data),encoding="utf-8");result=verify_admission(path,SHA);assert result["valid"] is False and result["errors"]==["control kms_object_lock evidence is expired or future-dated"]
