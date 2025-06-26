# White Board Backend

This is the backend for the White Board collaborative drawing app, built with Django and Django Channels for real-time WebSocket support. It manages rooms, users, permissions, and all real-time drawing events.

---

## Features

- Real-time collaboration via WebSockets (Django Channels)
- REST API for room and user management
- Room-based permissions (view/edit/admin)
- Undo/redo per user
- SQLite database by default (easy to switch to Postgres/MySQL)
- Django admin for management

---

## Getting Started

### Prerequisites

- Python 3.8+
- pip
- (Recommended) Virtualenv

### Installation

```bash
git clone https://github.com/TinkyGorai/WhiteBoard_backend
cd WhiteBoard_backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Database Setup

```bash
python manage.py migrate
```

### Running the Server

```bash
python manage.py runserver
```
The backend will be available at [http://127.0.0.1:8000/]

### Django Admin

Create a superuser to access the admin panel:
```bash
python manage.py createsuperuser
```
Then visit [http://127.0.0.1:8000/admin/]

---

## WebSocket Endpoint

- Default:  
  ```
  ws://localhost:8000/ws/whiteboard/<room_id>/
  ```
- The frontend connects to this endpoint for real-time drawing and collaboration.

---
