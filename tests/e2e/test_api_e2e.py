"""
End-to-end API tests.
Requires the full application stack running.
Run with: pytest tests/e2e/ --base-url http://localhost:8000
"""

import pytest
import httpx
import uuid


BASE_URL = "http://localhost:8000"


@pytest.fixture
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


@pytest.fixture
def async_client():
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)


class TestHealthEndpoints:

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "version" in data
        assert "uptime_seconds" in data

    def test_liveness_probe(self, client):
        response = client.get("/live")
        assert response.status_code == 200
        assert response.json()["alive"] is True

    def test_readiness_probe(self, client):
        response = client.get("/ready")
        assert response.status_code in [200, 503]


class TestChatEndpoint:

    def test_basic_chat_response(self, client):
        payload = {
            "message": "What is your return policy?",
            "prompt_strategy": "rag_standard",
        }
        response = client.post("/api/v1/chat/", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "answer" in data
        assert len(data["answer"]) > 0
        assert "conversation_id" in data
        assert "sources" in data
        assert "confidence" in data
        assert 0.0 <= data["confidence"] <= 1.0

    def test_multi_turn_conversation(self, client):
        conv_id = str(uuid.uuid4())

        # First turn
        r1 = client.post("/api/v1/chat/", json={
            "message": "How do I reset my password?",
            "conversation_id": conv_id,
        })
        assert r1.status_code == 200
        assert r1.json()["conversation_id"] == conv_id

        # Second turn - follow-up
        r2 = client.post("/api/v1/chat/", json={
            "message": "What if I don't get the email?",
            "conversation_id": conv_id,
        })
        assert r2.status_code == 200
        assert r2.json()["conversation_id"] == conv_id
        # Follow-up should be reformulated
        assert r2.json().get("reformulated_query") is not None

    def test_user_context_accepted(self, client):
        response = client.post("/api/v1/chat/", json={
            "message": "I need help with my account.",
            "user_context": {
                "customer_name": "Jane Doe",
                "account_tier": "premium",
                "technical_level": "advanced",
            },
        })
        assert response.status_code == 200

    def test_cot_strategy(self, client):
        response = client.post("/api/v1/chat/", json={
            "message": "My order is missing, what should I do?",
            "prompt_strategy": "chain_of_thought",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["answer"]

    def test_empty_message_rejected(self, client):
        response = client.post("/api/v1/chat/", json={"message": "   "})
        assert response.status_code == 422

    def test_message_too_long_rejected(self, client):
        response = client.post("/api/v1/chat/", json={"message": "x" * 3000})
        assert response.status_code == 422

    def test_response_metadata_present(self, client):
        response = client.post("/api/v1/chat/", json={
            "message": "How do I cancel my subscription?"
        })
        assert response.status_code == 200
        data = response.json()
        metadata = data.get("metadata", {})
        assert "latency_ms" in metadata
        assert "tokens_used" in metadata
        assert metadata["latency_ms"] > 0

    def test_clear_conversation(self, client):
        conv_id = str(uuid.uuid4())

        # Create conversation
        client.post("/api/v1/chat/", json={
            "message": "Hello",
            "conversation_id": conv_id,
        })

        # Clear it
        response = client.delete(f"/api/v1/chat/{conv_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "cleared"

    def test_feedback_endpoint(self, client):
        response = client.post("/api/v1/chat/feedback", json={
            "conversation_id": str(uuid.uuid4()),
            "message_index": 0,
            "rating": 5,
            "was_helpful": True,
            "feedback_text": "Very helpful, thank you!",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


class TestAdminEndpoints:

    def test_get_stats(self, client):
        response = client.get("/api/v1/admin/stats")
        assert response.status_code == 200
        data = response.json()
        assert "vector_store_count" in data
        assert "document_count" in data
        assert "llm_requests" in data

    def test_document_upload(self, client, tmp_path):
        # Create a test document
        test_file = tmp_path / "test.md"
        test_file.write_text(
            "# Test Document\n\nThis is test content for upload testing."
        )

        with open(test_file, "rb") as f:
            response = client.post(
                "/api/v1/admin/documents/upload",
                files={"file": ("test.md", f, "text/markdown")},
                params={"chunk_strategy": "hierarchical"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"

    def test_unsupported_file_type_rejected(self, client, tmp_path):
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"fake binary")

        with open(test_file, "rb") as f:
            response = client.post(
                "/api/v1/admin/documents/upload",
                files={"file": ("test.exe", f, "application/octet-stream")},
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_evaluation_endpoint(self, async_client):
        async with async_client as ac:
            response = await ac.post(
                "/api/v1/admin/evaluate",
                json={
                    "samples": [
                        {
                            "question": "How do I reset my password?",
                            "answer": "Click Forgot Password on the login page.",
                            "contexts": [
                                "To reset your password, click Forgot Password."
                            ],
                            "ground_truth": (
                                "Click Forgot Password on the login page."
                            ),
                        }
                    ],
                    "dataset_name": "e2e_test",
                    "use_llm_metrics": False,
                    "use_statistical_metrics": True,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "overall_pass_rate" in data
            assert "metric_averages" in data