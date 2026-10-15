"""
tests/load/locustfile.py — Locust Load Test for the Customer Support Chatbot API
You cannot claim production-ready without load test results.
"""

import random
from locust import HttpUser, between, task


SAMPLE_QUESTIONS = [
    "What is your return policy?",
    "How do I reset my password?",
    "Where is my order?",
    "Can I get a refund?",
    "How do I cancel my subscription?",
    "What payment methods do you accept?",
    "How long does shipping take?",
    "I was charged twice, what do I do?",
    "How do I change my email address?",
    "My order arrived damaged, what now?",
]

CONVERSATION_IDS = [f"load-test-{i}" for i in range(100)]


class ChatbotUser(HttpUser):
    """
    Simulates realistic chatbot usage.
    Run with: locust -f tests/load/locustfile.py --host http://localhost:8000
    """
    wait_time = between(1, 5)   # 1-5 seconds between requests

    def on_start(self):
        """Start a new conversation session."""
        self.conversation_id = random.choice(CONVERSATION_IDS)
        self.headers = {"X-API-Key": "dev-key-12345"}

    @task(70)  # 70% of traffic - single questions
    def ask_single_question(self):
        question = random.choice(SAMPLE_QUESTIONS)
        self.client.post(
            "/api/v1/chat/",
            json={
                "message": question,
                "prompt_strategy": "rag_standard",
            },
            headers=self.headers,
            name="/api/v1/chat/ [single]",
        )

    @task(20)  # 20% - conversational
    def ask_followup(self):
        conv_id = random.choice(CONVERSATION_IDS)
        self.client.post(
            "/api/v1/chat/",
            json={
                "message": random.choice(SAMPLE_QUESTIONS),
                "conversation_id": conv_id,
            },
            headers=self.headers,
            name="/api/v1/chat/ [conversational]",
        )

    @task(5)   # 5% - streaming
    def streaming_request(self):
        self.client.post(
            "/api/v1/chat/",
            json={
                "message": random.choice(SAMPLE_QUESTIONS),
                "stream": True,
            },
            headers=self.headers,
            name="/api/v1/chat/ [stream]",
        )

    @task(3)   # 3% - health checks
    def health_check(self):
        self.client.get("/health", name="/health")

    @task(2)   # 2% - stats
    def check_stats(self):
        self.client.get(
            "/api/v1/admin/stats",
            headers=self.headers,
            name="/api/v1/admin/stats",
        )