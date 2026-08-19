from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_API_TOKEN"] = "test-admin-token"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["ADMIN_UI_SESSION_SECRET"] = "test-session-secret-that-is-long-enough"
os.environ["AES_KEY"] = "0123456789abcdef0123456789abcdef"
os.environ["AES_IV"] = "0123456789abcdef"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.crypto import aes_decrypt, aes_encrypt
from app.main import app
from app.models import ClientTask, Config, Device, Order, User


class V2ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(bind=cls.engine)

    def setUp(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.session_factory()
        self.user = User(name="V2 user", api_key="valid-key", max_devices=2)
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.db.add(Device(user_id=self.user.id, device_id="device-1", device_name="Desktop"))
        self.db.commit()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_db, None)
        self.db.close()

    @staticmethod
    def _encrypted(data: dict) -> dict[str, str]:
        return {"payload": aes_encrypt(data)}

    @staticmethod
    def _decrypted_response(response) -> dict:
        return aes_decrypt(response.json()["payload"])

    def test_auth_returns_configured_lark_key(self) -> None:
        self.user.lark_key = "configured-lark-key"
        self.db.commit()

        response = self.client.post(
            "/v2/auth",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "device_id": "device-1",
                }
            ),
        )

        self.assertEqual(200, response.status_code)
        body = self._decrypted_response(response)
        self.assertEqual(0, body["code"])
        self.assertEqual("configured-lark-key", body["data"]["lark_key"])

    def test_order_upload_requires_task_id_and_saves_structured_holders(self) -> None:
        response = self.client.post(
            "/v2/orders",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "task_id": "task-001",
                    "device_id": "device-1",
                    "order_ip": "203.0.113.10",
                    "match_id": 86,
                    "ticket_holders": [
                        {
                            "name": "张三",
                            "phone": "13800000000",
                            "region": "A区",
                            "price": 280,
                        }
                    ],
                    "first_delay": 0,
                    "task_type": 1,
                }
            ),
        )

        self.assertEqual(201, response.status_code)
        self.assertEqual("task-001", self._decrypted_response(response)["data"]["task_id"])
        order = self.db.query(Order).one()
        self.assertEqual("task-001", order.task_id)
        self.assertEqual("203.0.113.10", order.order_ip)
        self.assertEqual(1, order.ticket_count)
        self.assertEqual("张三", order.order_names)
        self.assertIsNone(order.order_cards)
        self.assertEqual("280", order.order_price)
        holder = json.loads(order.ticket_holders_json)[0]
        self.assertEqual("张三", holder["name"])
        self.assertNotIn("card", holder)
        self.assertIsNone(order.first_start_t)
        self.assertIsNone(order.first_end_t)

    def test_order_upload_rejects_removed_identity_card_field(self) -> None:
        response = self.client.post(
            "/v2/orders",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "task_id": "task-with-card",
                    "device_id": "device-1",
                    "order_ip": "203.0.113.10",
                    "ticket_holders": [{"name": "张三", "card": "510000"}],
                }
            ),
        )

        self.assertEqual(422, response.status_code)
        body = self._decrypted_response(response)
        self.assertEqual(-422, body["code"])
        self.assertEqual("ticket_holders.0.card", body["data"]["errors"][0]["field"])
        self.assertEqual(0, self.db.query(Order).count())

    def test_order_upload_rejects_removed_time_fields(self) -> None:
        response = self.client.post(
            "/v2/orders",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "task_id": "task-002",
                    "device_id": "device-1",
                    "order_ip": "203.0.113.10",
                    "first_start_t": "2026-08-01T10:00:00+08:00",
                }
            ),
        )

        self.assertEqual(422, response.status_code)
        self.assertEqual(-422, self._decrypted_response(response)["code"])
        self.assertEqual(0, self.db.query(Order).count())

    def test_order_upload_rejects_missing_task_id(self) -> None:
        response = self.client.post(
            "/v2/orders",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "device_id": "device-1",
                    "order_ip": "203.0.113.10",
                }
            ),
        )

        self.assertEqual(422, response.status_code)
        self.assertEqual(-422, self._decrypted_response(response)["code"])

    def test_invalid_ciphertext_returns_plain_envelope_error(self) -> None:
        response = self.client.post("/v2/orders", json={"payload": "not-base64"})

        self.assertEqual(400, response.status_code)
        self.assertEqual(-4001, response.json()["code"])

    def test_business_error_response_is_encrypted(self) -> None:
        response = self.client.post(
            "/v2/orders",
            json=self._encrypted(
                {
                    "api_key": "unknown-key",
                    "task_id": "task-unknown",
                    "device_id": "device-1",
                    "order_ip": "203.0.113.10",
                }
            ),
        )

        self.assertEqual(401, response.status_code)
        self.assertEqual(-1001, self._decrypted_response(response)["code"])
        self.assertEqual(0, self.db.query(Order).count())

    def test_current_match_config_does_not_require_api_key(self) -> None:
        match_file = Path(__file__).parents[1] / "app" / "resources" / "match.json"
        match_id = json.loads(match_file.read_text(encoding="utf-8"))["id"]
        self.db.add(Config(match_id=match_id, content="Latest notice"))
        self.db.commit()

        for request_data in ({}, {"api_key": ""}, {"api_key": "unknown-key"}):
            with self.subTest(request_data=request_data):
                response = self.client.post(
                    "/v2/matches/current/config",
                    json=self._encrypted(request_data),
                )
                body = self._decrypted_response(response)

                self.assertEqual(200, response.status_code)
                self.assertEqual(0, body["code"])
                self.assertEqual(match_id, body["data"]["info"]["id"])
                self.assertEqual("Latest notice", body["data"]["notice"])

    def test_task_report_tracks_tasks_by_api_key_and_device(self) -> None:
        self.db.add(Device(user_id=self.user.id, device_id="device-2", device_name="Laptop"))
        self.db.commit()

        def report(device_id: str, task_id: str, action: str, status: str):
            return self.client.post(
                "/v2/tasks/report",
                json=self._encrypted(
                    {
                        "api_key": "valid-key",
                        "device_id": device_id,
                        "task_id": task_id,
                        "action": action,
                        "status": status,
                    }
                ),
            )

        first = self._decrypted_response(report("device-1", "task-001", "add", "online"))
        duplicate = self._decrypted_response(report("device-1", "task-001", "add", "online"))
        changed = self._decrypted_response(report("device-1", "task-001", "add", "offline"))
        second_device = self._decrypted_response(report("device-2", "task-001", "add", "online"))
        deleted = self._decrypted_response(report("device-1", "task-001", "delete", "offline"))
        deleted_again = self._decrypted_response(report("device-1", "task-001", "delete", "offline"))

        self.assertTrue(first["data"]["changed"])
        self.assertFalse(duplicate["data"]["changed"])
        self.assertTrue(changed["data"]["changed"])
        self.assertEqual("offline", changed["data"]["status"])
        self.assertEqual(1, second_device["data"]["device_task_count"])
        self.assertEqual(2, second_device["data"]["api_key_task_count"])
        self.assertTrue(deleted["data"]["changed"])
        self.assertEqual(1, deleted["data"]["api_key_task_count"])
        self.assertFalse(deleted_again["data"]["changed"])

        tasks = self.db.query(ClientTask).all()
        self.assertEqual(1, len(tasks))
        self.assertEqual("device-2", tasks[0].device_id)
        self.assertEqual("online", tasks[0].status)

    def test_task_report_rejects_unbound_device_and_invalid_status(self) -> None:
        unbound_response = self.client.post(
            "/v2/tasks/report",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "device_id": "missing-device",
                    "task_id": "task-001",
                    "action": "add",
                    "status": "online",
                }
            ),
        )
        invalid_response = self.client.post(
            "/v2/tasks/report",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "device_id": "device-1",
                    "task_id": "task-001",
                    "action": "add",
                    "status": "busy",
                }
            ),
        )

        self.assertEqual(404, unbound_response.status_code)
        self.assertEqual(-1003, self._decrypted_response(unbound_response)["code"])
        self.assertEqual(422, invalid_response.status_code)
        self.assertEqual(-422, self._decrypted_response(invalid_response)["code"])

    def test_live_tasks_page_groups_api_key_device_and_task_tags(self) -> None:
        self.db.add(
            ClientTask(
                user_id=self.user.id,
                device_id="device-1",
                task_id="task-online",
                status="online",
            )
        )
        self.db.add(
            ClientTask(
                user_id=self.user.id,
                device_id="device-1",
                task_id="task-offline",
                status="offline",
            )
        )
        self.db.commit()

        unauthenticated_delete = self.client.post(
            "/admin-ui/live-tasks/delete-all",
            follow_redirects=False,
        )
        self.assertEqual(302, unauthenticated_delete.status_code)
        self.assertTrue(unauthenticated_delete.headers["location"].startswith("/admin-ui/login"))
        self.assertEqual(2, self.db.query(ClientTask).count())

        login = self.client.post(
            "/admin-ui/login",
            data={"password": "test-admin-password", "next": "/admin-ui/live-tasks"},
            follow_redirects=False,
        )
        page = self.client.get("/admin-ui/live-tasks")
        data = self.client.get("/admin-ui/live-tasks/data")

        self.assertEqual(302, login.status_code)
        self.assertEqual(200, page.status_code)
        self.assertIn("实时任务", page.text)
        self.assertIn("task-online", page.text)
        self.assertIn("task-offline", page.text)
        self.assertIn('id="live-task-refresh"', page.text)
        self.assertIn('id="live-task-delete-all"', page.text)
        self.assertNotIn("setInterval", page.text)
        self.assertEqual(200, data.status_code)
        group = data.json()["groups"][0]
        self.assertEqual("valid-key", group["api_key"])
        self.assertEqual(2, group["task_count"])
        self.assertEqual("Desktop", group["devices"][0]["device_name"])

        delete_response = self.client.post(
            "/admin-ui/live-tasks/delete-all",
            follow_redirects=False,
        )
        self.assertEqual(302, delete_response.status_code)
        self.assertEqual("/admin-ui/live-tasks", delete_response.headers["location"])
        self.assertEqual(0, self.db.query(ClientTask).count())

    def test_admin_ui_defaults_to_live_tasks(self) -> None:
        anonymous = self.client.get("/admin-ui", follow_redirects=False)
        login_page = self.client.get("/admin-ui/login")
        login = self.client.post(
            "/admin-ui/login",
            data={"password": "test-admin-password"},
            follow_redirects=False,
        )
        dashboard = self.client.get("/admin-ui", follow_redirects=False)

        self.assertEqual(302, anonymous.status_code)
        self.assertIn("next=/admin-ui/live-tasks", anonymous.headers["location"])
        self.assertEqual(200, login_page.status_code)
        self.assertIn('name="next" value="/admin-ui"', login_page.text)
        self.assertEqual(302, login.status_code)
        self.assertEqual("/admin-ui/live-tasks", login.headers["location"])
        self.assertEqual(302, dashboard.status_code)
        self.assertEqual("/admin-ui/live-tasks", dashboard.headers["location"])

    def test_order_upload_rejects_invalid_order_ip(self) -> None:
        response = self.client.post(
            "/v2/orders",
            json=self._encrypted(
                {
                    "api_key": "valid-key",
                    "task_id": "task-invalid-ip",
                    "device_id": "device-1",
                    "order_ip": "203.0.113.10:8080",
                }
            ),
        )

        self.assertEqual(422, response.status_code)
        body = self._decrypted_response(response)
        self.assertEqual(-422, body["code"])
        self.assertEqual("order_ip", body["data"]["errors"][0]["field"])
        self.assertEqual(0, self.db.query(Order).count())

    def test_admin_api_uses_bearer_token_instead_of_password_query(self) -> None:
        password_response = self.client.get(
            "/v2/admin/users",
            params={"password": "test-admin-token"},
        )
        token_response = self.client.get(
            "/v2/admin/users",
            headers={"Authorization": "Bearer test-admin-token"},
        )

        self.assertEqual(401, password_response.status_code)
        self.assertEqual(200, token_response.status_code)
        self.assertEqual(self.user.id, token_response.json()["data"]["users"][0]["id"])


if __name__ == "__main__":
    unittest.main()
