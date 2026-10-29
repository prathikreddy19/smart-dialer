import io

from starlette.datastructures import UploadFile

from app.api.database import reset_database
from app.api.upload import upload_dataset
from app.api.health import health_check
from app.database.database import SessionLocal
from app.main import app


def test_swagger_schema_contains_required_routes():
    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/database/reset" in paths
    assert "/upload/dataset" in paths
    assert "/campaigns/{campaign_id}/dial" in paths
    assert "/metrics" in paths


def test_health_checks_database_and_reset_succeeds():
    with SessionLocal() as db:
        assert health_check(db) == {"status": "healthy", "database": "connected"}
    assert reset_database()["status"] == "success"


def test_multi_file_upload_imports_in_dependency_order():
    def file(name: str, content: str) -> UploadFile:
        return UploadFile(filename=name, file=io.BytesIO(content.encode("utf-8")))

    result = upload_dataset(
        vendor_telephony=file("vendor_telephony.csv", "vendor_id,vendor_name,vendor_account_id,timezone,status,schema_version\nV1,Vendor,ACC,UTC,ACTIVE,1\n"),
        campaigns=file("campaigns.csv", "campaign_id,campaign_name,channel,strategy_version,start_at,target_definition,end_at\nC1,Campaign,VOICE,1,2025-01-01 00:00:00,all,\n"),
        borrowers=file("borrowers.csv", "borrower_id,name,phone,email,city,created_at,updated_at,state\nB1,Borrower,123,,City,2025-01-01 00:00:00,2025-01-01 00:00:00,CA\n"),
        agents=file("agents.csv", "agent_id,employee_code,agent_name,vendor_id,team,status,joined_at,updated_at\nA1,E1,Agent,V1,T,ACTIVE,2025-01-01 00:00:00,2025-01-01 00:00:00\n"),
        calls=file("calls.csv", "call_id,account_id,borrower_id,event_at,agent_id,campaign_id,direction,vendor_id,call_status,duration_sec,timezone\nH1,ACC,B1,2025-01-01 00:00:00,A1,C1,OUTBOUND,V1,COMPLETED,10,UTC\n"),
        call_attempts=file("call_attempts.csv", "attempt_id,account_id,borrower_id,event_at,call_id,agent_id,attempt_no,vendor_id,attempt_status\nT1,ACC,B1,2025-01-01 00:00:00,H1,A1,1,V1,COMPLETED\n"),
        agent_sessions=file("agent_sessions.csv", "session_id,agent_id,login_at,channel,device_id,timezone,logout_at\nS1,A1,2025-01-01 00:00:00,VOICE,D1,UTC,\n"),
    )
    assert result["status"] == "success"
    assert [row["file"] for row in result["files"]] == [
        "vendor_telephony.csv", "campaigns.csv", "borrowers.csv", "agents.csv",
        "calls.csv", "call_attempts.csv", "agent_sessions.csv",
    ]
