-- UAV 无人机控制系统 - 数据库初始化 v2.0

CREATE DATABASE IF NOT EXISTS uav_swarm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE uav_swarm;

-- 飞行器表
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id   INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(32),
    model        VARCHAR(32),
    last_seen    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 集群任务主表
CREATE TABLE IF NOT EXISTS swarm_mission (
    swarm_id     INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(64),
    drone_count  INT DEFAULT 0,
    region_json  TEXT COMMENT '作业区域 GeoJSON',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    status       TINYINT DEFAULT 0 COMMENT '0=待分配 1=执行中 2=已完成 3=失败'
) ENGINE=InnoDB;

-- 子任务表（每架无人机的飞行任务）
CREATE TABLE IF NOT EXISTS mission (
    mission_id   INT AUTO_INCREMENT PRIMARY KEY,
    swarm_id     INT DEFAULT NULL,
    vehicle_id   INT NOT NULL,
    task_name    VARCHAR(64),
    target_x     DOUBLE,
    target_y     DOUBLE,
    target_z     DOUBLE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    status       TINYINT DEFAULT 0 COMMENT '0=待执行 1=执行中 2=已完成 3=失败',
    FOREIGN KEY (swarm_id) REFERENCES swarm_mission(swarm_id) ON DELETE CASCADE,
    INDEX idx_vehicle_status (vehicle_id, status),
    INDEX idx_swarm (swarm_id)
) ENGINE=InnoDB;

-- 航点表
CREATE TABLE IF NOT EXISTS waypoint (
    waypoint_id  INT AUTO_INCREMENT PRIMARY KEY,
    mission_id   INT NOT NULL,
    seq          INT COMMENT '航点序号',
    wp_x         DOUBLE,
    wp_y         DOUBLE,
    wp_z         DOUBLE,
    FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE CASCADE,
    INDEX idx_mission_seq (mission_id, seq)
) ENGINE=InnoDB;

-- 飞行日志表
CREATE TABLE IF NOT EXISTS flight_logs (
    log_id       INT AUTO_INCREMENT PRIMARY KEY,
    mission_id   INT,
    vehicle_id   INT,
    start_time   DATETIME,
    end_time     DATETIME,
    result       TINYINT DEFAULT 0 COMMENT '0=未知 1=成功 2=超时 3=中止',
    actual_x     DOUBLE,
    actual_y     DOUBLE,
    actual_z     DOUBLE,
    error_dist   DOUBLE COMMENT '与目标点距离误差(米)',
    remarks      TEXT,
    FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE SET NULL,
    INDEX idx_vehicle_time (vehicle_id, start_time)
) ENGINE=InnoDB;

-- 控制指令表
CREATE TABLE IF NOT EXISTS command_control (
    command_id       INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id       INT NOT NULL,
    mission_id       INT DEFAULT NULL,
    command_type     VARCHAR(32),
    command_params   TEXT COMMENT 'JSON 参数',
    issued_by        VARCHAR(64),
    issued_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    ack_status       TINYINT DEFAULT 0 COMMENT '0=未应答 1=已接收 2=执行中 3=完成 4=失败',
    result_msg       TEXT,
    FOREIGN KEY (mission_id) REFERENCES mission(mission_id) ON DELETE SET NULL,
    INDEX idx_vehicle_time (vehicle_id, issued_at)
) ENGINE=InnoDB;

-- 插入默认无人机（如果不存在）
INSERT IGNORE INTO vehicles (vehicle_id, name, model) VALUES
    (1, 'Drone-01', 'gz_x500'),
    (2, 'Drone-02', 'gz_x500'),
    (3, 'Drone-03', 'gz_x500'),
    (4, 'Drone-04', 'gz_x500');

-- 创建测试任务（可选）
-- INSERT INTO mission (vehicle_id, task_name, target_x, target_y, target_z, status)
-- VALUES (1, 'Test Mission', 10.0, 10.0, 5.0, 0);
