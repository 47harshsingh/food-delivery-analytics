-- Food delivery analytics: schema (MySQL 8.0+)

CREATE DATABASE IF NOT EXISTS food_delivery;
USE food_delivery;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS delivery_partners;
DROP TABLE IF EXISTS restaurants;
DROP TABLE IF EXISTS promotions;
DROP TABLE IF EXISTS zones;

CREATE TABLE zones (
    zone_id     SMALLINT     PRIMARY KEY,
    zone_name   VARCHAR(50)  NOT NULL,
    city        VARCHAR(30)  NOT NULL
);

CREATE TABLE restaurants (
    restaurant_id    SMALLINT      PRIMARY KEY,
    restaurant_name  VARCHAR(80)   NOT NULL,
    zone_id          SMALLINT      NOT NULL,
    cuisine          VARCHAR(30)   NOT NULL,
    commission_rate  DECIMAL(4,2)  NOT NULL,   -- share of gross order value the platform keeps
    onboarded_date   DATE          NOT NULL,
    FOREIGN KEY (zone_id) REFERENCES zones (zone_id)
);

CREATE TABLE delivery_partners (
    partner_id    SMALLINT     PRIMARY KEY,
    zone_id       SMALLINT     NOT NULL,       -- home zone
    vehicle_type  VARCHAR(20)  NOT NULL,
    joined_date   DATE         NOT NULL,
    FOREIGN KEY (zone_id) REFERENCES zones (zone_id)
);

CREATE TABLE promotions (
    promo_id         TINYINT       PRIMARY KEY,
    promo_code       VARCHAR(20)   NOT NULL UNIQUE,
    campaign_name    VARCHAR(80)   NOT NULL,
    discount_type    ENUM('percent', 'flat') NOT NULL,
    discount_value   DECIMAL(8,2)  NOT NULL,   -- % for percent, INR for flat
    max_discount     DECIMAL(8,2)  NOT NULL,
    min_order_value  DECIMAL(8,2)  NOT NULL,
    free_delivery    TINYINT(1)    NOT NULL,
    start_date       DATE          NOT NULL,
    end_date         DATE          NOT NULL,
    eligibility      VARCHAR(20)   NOT NULL    -- any / first_order / weekend / lunch
);

CREATE TABLE customers (
    customer_id  INT          PRIMARY KEY,
    zone_id      SMALLINT     NOT NULL,
    signup_date  DATE         NOT NULL,
    platform     VARCHAR(10)  NOT NULL,
    FOREIGN KEY (zone_id) REFERENCES zones (zone_id)
);

CREATE TABLE orders (
    order_id          INT           PRIMARY KEY,
    customer_id       INT           NOT NULL,
    restaurant_id     SMALLINT      NOT NULL,
    partner_id        SMALLINT      NOT NULL,
    zone_id           SMALLINT      NOT NULL,  -- delivery zone
    promo_id          TINYINT       NULL,      -- NULL = organic (no discount)
    order_ts          DATETIME      NOT NULL,
    gross_amount      DECIMAL(10,2) NOT NULL,  -- menu value of the basket
    discount_amount   DECIMAL(10,2) NOT NULL,  -- platform-funded
    net_amount        DECIMAL(10,2) NOT NULL,  -- gross - discount (AOV and GMV use this)
    delivery_fee      DECIMAL(8,2)  NOT NULL,
    partner_payout    DECIMAL(8,2)  NOT NULL,
    prep_minutes      SMALLINT      NOT NULL,  -- order placed -> food ready
    travel_minutes    SMALLINT      NOT NULL,  -- food ready -> delivered
    delivery_minutes  SMALLINT      NOT NULL,  -- prep + travel
    is_refunded       TINYINT(1)    NOT NULL,
    refund_amount     DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (customer_id)   REFERENCES customers (customer_id),
    FOREIGN KEY (restaurant_id) REFERENCES restaurants (restaurant_id),
    FOREIGN KEY (partner_id)    REFERENCES delivery_partners (partner_id),
    FOREIGN KEY (zone_id)       REFERENCES zones (zone_id),
    FOREIGN KEY (promo_id)      REFERENCES promotions (promo_id),
    INDEX idx_orders_customer_ts (customer_id, order_ts),
    INDEX idx_orders_restaurant (restaurant_id),
    INDEX idx_orders_ts (order_ts)
);

CREATE TABLE order_items (
    order_item_id  INT           PRIMARY KEY,
    order_id       INT           NOT NULL,
    item_name      VARCHAR(60)   NOT NULL,
    category       VARCHAR(20)   NOT NULL,
    quantity       TINYINT       NOT NULL,
    unit_price     DECIMAL(8,2)  NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
);
