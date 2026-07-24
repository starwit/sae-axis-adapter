import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from visionapi.common_pb2 import MessageType
from visionapi.sae_pb2 import SaeMessage

from axisadapter.config import (AxisAdapterConfig, ClassMapping,
                                FrameShapeConfig, MqttConfig, RedisConfig)
from axisadapter.stage import run_stage

SAMPLE_PAYLOAD = (Path(__file__).parent / 'data' / 'single.jsonl').read_bytes()


@pytest.fixture(autouse=True)
def disable_prometheus():
    # We don't want to start the Prometheus server during tests
    with patch('axisadapter.stage.start_http_server'):
        yield

@pytest.fixture
def set_config():
    with patch('axisadapter.stage.AxisAdapterConfig') as mock_config:
        def _make_mock_config(stream_id: str):
            mock_config.return_value = AxisAdapterConfig(
                log_level='WARNING',
                redis=RedisConfig(stream_id=stream_id),
                mqtt=MqttConfig(topic='axis/detections'),
                frame_shape=FrameShapeConfig(width=1920, height=1080),
                class_mapping={'Car': ClassMapping(id=2, name='car')},
            )
        yield _make_mock_config

@pytest.fixture
def redis_publisher_mock():
    with patch('axisadapter.stage.ValkeyPublisher') as mock_publisher:
        yield mock_publisher.return_value.__enter__.return_value

@pytest.fixture
def mqtt_client_mock():
    with patch('axisadapter.stage.mqtt.Client') as mock_client:
        yield mock_client.return_value

def test_example(set_config, redis_publisher_mock, mqtt_client_mock):
    set_config(stream_id='test_stream')

    # Deliver a message via the registered on_message callback once the loop starts,
    # then release the stop event so run_stage() returns.
    stop_event = threading.Event()

    def deliver_messages():
        msg = SimpleNamespace(payload=SAMPLE_PAYLOAD, topic='axis/detections')
        mqtt_client_mock.on_message(mqtt_client_mock, None, msg)
        stop_event.set()

    mqtt_client_mock.loop_start.side_effect = deliver_messages

    with patch('axisadapter.stage.threading.Event', return_value=stop_event):
        run_stage()

    # The adapter subscribed to the configured topic and connected/disconnected cleanly
    mqtt_client_mock.connect.assert_called_once()
    mqtt_client_mock.loop_stop.assert_called_once()
    mqtt_client_mock.disconnect.assert_called_once()

    # Exactly one SAE message was published to the configured output stream
    assert redis_publisher_mock.call_count == 1
    stream_key, proto_data = redis_publisher_mock.call_args_list[0].args
    assert stream_key == 'axisadapter:test_stream'

    sae_msg = SaeMessage()
    sae_msg.ParseFromString(proto_data)
    assert sae_msg.type == MessageType.SAE
    assert sae_msg.frame.source_id == 'test_stream'
    # 2 of the 4 sample detections are classified (both cars)
    assert len(sae_msg.detections) == 2
    assert all(d.class_id == 2 for d in sae_msg.detections)
    assert sae_msg.model_metadata.class_names[2] == 'car'
