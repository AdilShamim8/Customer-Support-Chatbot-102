# Contributing to Customer Support Chatbot

Thank you for considering a contribution! This document explains
our development process, coding standards, and how to get started.

## Development Setup

```bash
git clone https://github.com/AdilShamim8/Customer-Support-Chatbot-102.git
cd Customer-Support-Chatbot-102
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pre-commit install
cp .env.example .env
# Set OPENAI_API_KEY in .env