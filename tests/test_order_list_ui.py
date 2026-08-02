from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("AES_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("AES_IV", "0123456789abcdef")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Order, User
from app.routers.order_query_ui import router
from app.services.order_query import query_orders_by_api_key


class OrderListUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.session_factory = sessionmaker(bind=cls.engine)

    def setUp(self) -> None:
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.session_factory()
        self.user = User(name="测试用户", api_key="valid-key")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self) -> None:
        self.db.close()

    def _client(self) -> TestClient:
        app = FastAPI()
        app.include_router(router)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        return TestClient(app)

    def test_service_rejects_unknown_key(self) -> None:
        result = query_orders_by_api_key(self.db, "missing-key")
        self.assertFalse(result.key_valid)
        self.assertEqual([], result.orders)
        self.assertEqual(0, result.total)

    def test_service_filters_and_paginates_orders_newest_first(self) -> None:
        earlier = datetime(2026, 7, 18, 8, 0, 0)
        self.db.add_all(
            [
                Order(
                    user_id=self.user.id,
                    raw_api_key="valid-key",
                    device_name="设备 A",
                    match_id=100,
                    order_names="张三",
                    order_region="A区",
                    order_price="280",
                    ticket_count=1,
                    type=0,
                    parse_status="ok",
                    created_at=earlier,
                ),
                Order(
                    user_id=None,
                    raw_api_key="valid-key",
                    device_name="设备 B",
                    match_id=101,
                    order_names="李四&王五",
                    order_region="B区",
                    order_price="480&480",
                    ticket_count=2,
                    type=1,
                    parse_status="unknown_key",
                    created_at=earlier + timedelta(minutes=1),
                ),
                Order(
                    user_id=self.user.id,
                    raw_api_key="valid-key",
                    device_name="设备 C",
                    match_id=100,
                    order_names="赵六",
                    order_region="C区",
                    order_price="680",
                    ticket_count=3,
                    type=0,
                    parse_status="ok",
                    created_at=earlier + timedelta(minutes=2),
                ),
            ]
        )
        self.db.commit()

        first_page = query_orders_by_api_key(
            self.db,
            "valid-key",
            match_id=100,
            page=1,
            page_size=1,
        )
        second_page = query_orders_by_api_key(
            self.db,
            "valid-key",
            match_id=100,
            page=99,
            page_size=1,
        )
        all_orders = query_orders_by_api_key(self.db, "valid-key", page_size=10)

        self.assertTrue(first_page.key_valid)
        self.assertEqual(2, first_page.total)
        self.assertEqual(4, first_page.tickets_sum)
        self.assertEqual(2, first_page.total_pages)
        self.assertEqual("设备 C", first_page.orders[0]["device_name"])
        self.assertEqual(2, second_page.page)
        self.assertEqual("设备 A", second_page.orders[0]["device_name"])
        self.assertEqual([100, 101, 100], [order["match_id"] for order in all_orders.orders])

    def test_page_renders_requested_columns_and_filter_state(self) -> None:
        self.db.add(
            Order(
                user_id=self.user.id,
                raw_api_key="valid-key",
                device_name="测试设备",
                match_id=100,
                order_names="张三",
                order_region="A区",
                order_price="280",
                ticket_count=1,
                type=0,
                parse_status="ok",
            )
        )
        self.db.commit()

        with patch(
            "app.routers.order_query_ui.check_query_rate_limit",
            side_effect=AssertionError("订单页面不应调用 IP 限流"),
        ):
            response = self._client().post(
                "/orders",
                data={
                    "api_key": "valid-key",
                    "match_id": "100",
                    "page_size": "10",
                    "page": "1",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertIn("测试设备", response.text)
        self.assertIn("张三", response.text)
        self.assertIn("A区", response.text)
        self.assertIn("共 1 条，合计 1 张票", response.text)
        self.assertIn('type="text" value="valid-key"', response.text)
        self.assertIn('<option value="10" selected>10 条</option>', response.text)
        self.assertIn("<th>比赛 ID</th>", response.text)
        self.assertIn("<th>创建时间</th>", response.text)
        self.assertNotIn("<th>类型</th>", response.text)

    def test_page_allows_consecutive_requests_without_rate_limit(self) -> None:
        with patch(
            "app.routers.order_query_ui.check_query_rate_limit",
            side_effect=AssertionError("订单页面不应调用 IP 限流"),
        ):
            client = self._client()
            first_response = client.post("/orders", data={"api_key": "wrong-key"})
            second_response = client.post("/orders", data={"api_key": "wrong-key"})

        self.assertEqual(200, first_response.status_code)
        self.assertEqual(200, second_response.status_code)
        self.assertIn("密钥不存在或无权查看订单", second_response.text)
        self.assertNotIn("秒后可查询", second_response.text)
        self.assertNotIn("订单记录", second_response.text)

    def test_page_rejects_invalid_match_id(self) -> None:
        response = self._client().post(
            "/orders",
            data={
                "api_key": "valid-key",
                "match_id": "not-a-number",
                "page_size": "20",
                "page": "1",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertIn("比赛 ID 必须是正整数", response.text)
        self.assertNotIn("订单列表", response.text)


if __name__ == "__main__":
    unittest.main()
