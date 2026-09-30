import asyncio
from datetime import datetime, timedelta

import aiosqlite

FMT = "%Y-%m-%d %H:%M"

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    price INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_name TEXT NOT NULL,
    service_id INTEGER NOT NULL REFERENCES services(id),
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    reminded INTEGER NOT NULL DEFAULT 0,
    username TEXT,
    phone TEXT
);
CREATE INDEX IF NOT EXISTS idx_app_start ON appointments(start, status);
CREATE TABLE IF NOT EXISTS masters (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, phone TEXT NOT NULL);
"""
# start/end — локальное время салона, формат 'YYYY-MM-DD HH:MM'; status: active | cancelled

_SELECT = """SELECT a.*, s.name AS service, s.price AS price
             FROM appointments a JOIN services s ON s.id = a.service_id"""


class DB:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn
        self.conn.row_factory = aiosqlite.Row
        self.lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: str, default_services=(), master_ids=()):
        conn = await aiosqlite.connect(path)
        db = cls(conn)
        await conn.executescript(SCHEMA)
        async with conn.execute("PRAGMA table_info(appointments)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        for col in ("username", "phone"):  # миграция старых баз
            if col not in cols:
                await conn.execute(f"ALTER TABLE appointments ADD COLUMN {col} TEXT")
        async with conn.execute("SELECT COUNT(*) FROM services") as cur:
            if (await cur.fetchone())[0] == 0:
                await conn.executemany(
                    "INSERT INTO services(name, duration_min, price) VALUES (?,?,?)", default_services)
        for m in master_ids:
            await conn.execute("INSERT OR IGNORE INTO masters(user_id) VALUES (?)", (m,))
        await conn.commit()
        return db

    async def close(self):
        await self.conn.close()

    async def _all(self, sql, args=()):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchall()

    async def _one(self, sql, args=()):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchone()

    # --- услуги
    async def services(self):
        return await self._all("SELECT * FROM services ORDER BY id")

    async def service(self, sid: int):
        return await self._one("SELECT * FROM services WHERE id=?", (sid,))

    # --- мастера
    async def is_master(self, uid: int) -> bool:
        return await self._one("SELECT 1 FROM masters WHERE user_id=?", (uid,)) is not None

    async def add_master(self, uid: int):
        await self.conn.execute("INSERT OR IGNORE INTO masters(user_id) VALUES (?)", (uid,))
        await self.conn.commit()

    async def remove_master(self, uid: int):
        await self.conn.execute("DELETE FROM masters WHERE user_id=?", (uid,))
        await self.conn.commit()

    async def master_ids(self):
        return [r[0] for r in await self._all("SELECT user_id FROM masters")]

    # --- записи
    async def busy(self, day: str):
        """Занятые интервалы дня [(start, end)]."""
        rows = await self._all(
            "SELECT start, end FROM appointments WHERE status='active' AND start LIKE ?", (day + "%",))
        return [(r["start"], r["end"]) for r in rows]

    async def client_phone(self, uid: int):
        row = await self._one("SELECT phone FROM clients WHERE user_id=?", (uid,))
        return row["phone"] if row else None

    async def set_client_phone(self, uid: int, phone: str):
        await self.conn.execute("INSERT OR REPLACE INTO clients(user_id, phone) VALUES (?,?)", (uid, phone))
        await self.conn.commit()

    async def create(self, user_id, user_name, service_id, start: datetime, end: datetime, reminded: bool,
                     username=None, phone=None):
        """Создаёт запись; None, если время уже занято."""
        s, e = start.strftime(FMT), end.strftime(FMT)
        async with self.lock:  # защита от двойного бронирования
            clash = await self._one(
                "SELECT 1 FROM appointments WHERE status='active' AND start < ? AND end > ?", (e, s))
            if clash:
                return None
            cur = await self.conn.execute(
                "INSERT INTO appointments(user_id,user_name,service_id,start,end,reminded,username,phone)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (user_id, user_name, service_id, s, e, int(reminded), username, phone))
            await self.conn.commit()
            return cur.lastrowid

    async def appointment(self, aid: int):
        return await self._one(_SELECT + " WHERE a.id=?", (aid,))

    async def user_upcoming(self, uid: int, now: datetime):
        return await self._all(
            _SELECT + " WHERE a.user_id=? AND a.status='active' AND a.end > ? ORDER BY a.start",
            (uid, now.strftime(FMT)))

    async def day(self, day: str):
        return await self._all(
            _SELECT + " WHERE a.status='active' AND a.start LIKE ? ORDER BY a.start", (day + "%",))

    async def cancel(self, aid: int) -> bool:
        cur = await self.conn.execute(
            "UPDATE appointments SET status='cancelled' WHERE id=? AND status='active'", (aid,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def due_reminders(self, now: datetime, hours: int):
        return await self._all(
            _SELECT + " WHERE a.status='active' AND a.reminded=0 AND a.start > ? AND a.start <= ?",
            (now.strftime(FMT), (now + timedelta(hours=hours)).strftime(FMT)))

    async def mark_reminded(self, aid: int):
        await self.conn.execute("UPDATE appointments SET reminded=1 WHERE id=?", (aid,))
        await self.conn.commit()
