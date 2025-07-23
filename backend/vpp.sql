CREATE DATABASE vpp_2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE vpp_2;

-- 0-1. entity: 발전소, 배터리, 아두이노 등 엔티티 정의
CREATE TABLE entity (
    entity_id INT PRIMARY KEY,
    entity_type ENUM('solar', 'wind', 'battery', 'grid', 'load') NOT NULL,
    entity_name VARCHAR(20) NOT NULL  -- 예: '태양광', '아두이노'
);

-- 0-2. relay: 엔티티 간 릴레이 연결 정의
CREATE TABLE relay (
    relay_id INT PRIMARY KEY AUTO_INCREMENT,
    source_entity_id INT NOT NULL,
    target_entity_id INT NOT NULL,
    description VARCHAR(30),
    FOREIGN KEY (source_entity_id) REFERENCES entity(entity_id),
    FOREIGN KEY (target_entity_id) REFERENCES entity(entity_id)
);

-- 1. node_status_log: 발전/저장/부하 상태 실시간 기록
CREATE TABLE node_status_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    node_timestamp DATETIME NOT NULL,
    relay_id int NOT NULL,
    power_kw FLOAT NOT NULL,
    soc FLOAT,                 -- NULL 허용 (배터리만)
    FOREIGN KEY (relay_id) REFERENCES relay(relay_id)
);

-- 2. relay_status_log: 릴레이 상태 변화 기록
CREATE TABLE relay_status (
    relay_id INT PRIMARY KEY,
    status TINYINT(1) NOT NULL CHECK (status IN (0, 1)),
    last_updated DATETIME NOT NULL,
    FOREIGN KEY (relay_id) REFERENCES relay(relay_id)
);

-- 3. bidding_log: LLM이 생성한 입찰 제안 정보
CREATE TABLE bidding_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    bid_time DATETIME NOT NULL,
    bid_id int NOT NULL,
    entity_id int NOT NULL,
    bid_quantity_kwh FLOAT NOT NULL,
    bid_price_per_kwh FLOAT NOT NULL,
    llm_reasoning TEXT,
    FOREIGN KEY (entity_id) REFERENCES entity(entity_id)
);

-- 4. bidding_result: 입찰 결과 및 행동 기록
CREATE TABLE bidding_result (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bid_id INT NOT NULL,
    entity_id INT NOT NULL,
    quantity_kwh FLOAT,
    bid_price FLOAT,
    result ENUM('accepted', 'rejected'),
    FOREIGN KEY (entity_id) REFERENCES entity(entity_id)
);


-- 5. weather
CREATE TABLE weather (
    obs_time DATETIME PRIMARY KEY,
    temperature_c FLOAT,
    rainfall_mm FLOAT,
    humidity_pct FLOAT,
    cloud_cover_okta INT,
    solar_irradiance FLOAT,
    wind_speed FLOAT
);


-- 6. smp
CREATE TABLE smp (
    smp_time DATETIME PRIMARY KEY,
    price_krw FLOAT NOT NULL
);


-- 7. profit_log
CREATE TABLE profit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    entity_id INT NOT NULL,
    unit_price FLOAT NOT NULL,
    revenue_krw FLOAT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entity(entity_id)
);



-- 데이터 삽입
-- entity 더미 데이터
INSERT INTO entity (entity_id, entity_type, entity_name) VALUES
(1, 'solar', '태양광'),
(2, 'wind', '풍력'),
(3, 'battery', '배터리'),
(4, 'load', '아두이노');

-- relay 더미 데이터
INSERT INTO relay (relay_id, source_entity_id, target_entity_id, description) VALUES
(1, 1, 4, '태양 - 부하'),
(2, 2, 4, '풍력 - 부하'),
(3, 3, 4, '배터리 - 부하'),
(4, 1, 3, '태양 - 배터리'),
(5, 2, 3, '풍력 - 배터리');

-- node_status_log 더미 데이터
INSERT INTO node_status_log (node_timestamp, relay_id, power_kw, soc) VALUES
('2025-07-21 10:00:00', 1, 0.45, NULL),
('2025-07-21 10:00:00', 2, 0.50, NULL),
('2025-07-21 10:00:00', 3, 0.30, 65.0),
('2025-07-21 10:00:00', 4, 0.20, 66.2),
('2025-07-21 10:00:00', 5, 0.10, 66.5);

-- relay_status 더미 데이터
INSERT INTO relay_status (relay_id, status, last_updated) VALUES
(1, 1, '2025-07-21 10:00:00'),
(2, 1, '2025-07-21 10:00:00'),
(3, 1, '2025-07-21 10:00:00'),
(4, 0, '2025-07-21 10:00:00'),
(5, 1, '2025-07-21 10:00:00');

-- bidding_log 더미 데이터
INSERT INTO bidding_log (bid_time, bid_id, entity_id, bid_quantity_kwh, bid_price_per_kwh, llm_reasoning) VALUES
('2025-07-21 10:00:00', 1, 1, 100, 120, '태양광 예측량이 높아 입찰 제안'),
('2025-07-21 10:00:00', 1, 2, 50, 125, '풍력 상태 양호, 가격 경쟁력 있음'),
('2025-07-21 10:00:00', 1, 3, 80, 130, '배터리 잔량 높음, 시장 반응 예상'),
('2025-07-21 11:00:00', 2, 1, 90, 122, '태양광 발전량 소폭 감소'),
('2025-07-21 11:00:00', 2, 2, 60, 124, '풍속 증가로 인한 생산 증가 예상'),
('2025-07-21 11:00:00', 2, 3, 70, 127, 'SOC 안정적, 방전 가능');


-- bidding_result 더미 데이터
INSERT INTO bidding_result (bid_id, entity_id, quantity_kwh, bid_price, result) VALUES
(1, 1, 95, 118, 'accepted'),
(1, 2, 48, 122, 'rejected'),
(1, 3, 75, 127, 'accepted'),
(2, 1, NULL, NULL, NULL),
(2, 2, 45, 123, 'accepted'),
(2, 3, NULL, NULL, NULL);


-- weather 더미 데이터
INSERT INTO weather (obs_time, temperature_c, rainfall_mm, humidity_pct, cloud_cover_okta, solar_irradiance, wind_speed) VALUES
('2025-07-21 09:00:00', 28.5, 0.0, 70, 2, 600, 3.2),
('2025-07-21 10:00:00', 29.0, 0.0, 65, 1, 750, 3.5),
('2025-07-21 11:00:00', 29.5, 0.0, 60, 0, 800, 3.8);

-- smp 더미 데이터
INSERT INTO smp (smp_time, price_krw) VALUES
('2025-07-21 09:00:00', 124.5),
('2025-07-21 10:00:00', 126.0),
('2025-07-21 11:00:00', 127.8);


-- profit_log 더미 데이터
INSERT INTO profit_log (timestamp, entity_id, unit_price, revenue_krw) VALUES
('2025-07-21 10:00:00', 1, 124.5, 1245.0),
('2025-07-21 10:00:00', 2, 125.0, 625.0),
('2025-07-21 10:00:00', 3, 123.0, 984.0),
('2025-07-21 11:00:00', 1, 126.5, 1138.5),
('2025-07-21 11:00:00', 2, 127.0, 762.0);


