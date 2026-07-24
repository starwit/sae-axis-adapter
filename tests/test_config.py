import pytest
from pydantic import ValidationError

from axisadapter.config import (AxisAdapterConfig, ClassMapping,
                                FrameShapeConfig, MqttConfig, RedisConfig)


def test_incomplete_config():
    with pytest.raises(ValidationError):
        AxisAdapterConfig(
            log_level="INFO",
            redis=RedisConfig(
                host="localhost",
                port=6379
                # Missing stream_id
            ),
            mqtt=MqttConfig(
                host="localhost",
                # Missing topic
            )
        )

def test_complete_config():
    config = AxisAdapterConfig(
        log_level="INFO",
        redis=RedisConfig(
            host="localhost",
            port=6379,
            stream_id="stream1"
        ),
        mqtt=MqttConfig(
            host="localhost",
            port=1883,
            topic="axis/detections",
            username="user",
            password="secret"
        ),
        frame_shape=FrameShapeConfig(width=1920, height=1080),
        class_mapping={
            "Car": ClassMapping(id=2, name="car"),
        },
        prometheus_port=9000
    )

    assert config.log_level.name == "INFO"
    assert config.redis.host == "localhost"
    assert config.redis.port == 6379
    assert config.redis.stream_id == "stream1"
    assert config.mqtt.host == "localhost"
    assert config.mqtt.port == 1883
    assert config.mqtt.topic == "axis/detections"
    assert config.mqtt.username == "user"
    assert config.class_mapping["Car"].id == 2
    assert config.class_mapping["Car"].name == "car"
    assert config.prometheus_port == 9000
