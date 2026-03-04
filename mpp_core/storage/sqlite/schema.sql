CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id_1688 TEXT NOT NULL UNIQUE,
    title TEXT,
    title_raw TEXT,
    title_en TEXT,
    title_ru TEXT,
    category_path_1688 TEXT,
    category_1688 TEXT,
    internal_category TEXT,
    category_internal TEXT,
    ozon_category_id INTEGER,
    category_ozon INTEGER,
    ozon_type_id INTEGER,
    price REAL,
    status TEXT NOT NULL CHECK (status IN ('new', 'translated', 'mapped', 'ready_for_export', 'exported')),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_products_item_id_1688 ON products (item_id_1688);
