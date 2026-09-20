-- 0021 景点照片:点开地图上的某个停留点时展示的那张图。
--
--  * 内容寻址(sha256),同一张图在同一趟行程里只占一份磁盘,和收据一个思路。
--  * 停留点自己只在 detail_json 里存 sha,不存 URL——URL 的前缀在私有页
--    和公开分享页是不同的,存死了分享出去就取不到。
--  * 公开分享页要能匿名取图,所以取图时按 trip_id 校验归属,再由分享 token
--    这一层决定能不能看;照片表本身不记是否公开。
CREATE TABLE IF NOT EXISTS trip_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    mime TEXT NOT NULL,
    bytes INTEGER,
    path TEXT NOT NULL,
    created_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_photos_uniq ON trip_photos(trip_id, sha256);
