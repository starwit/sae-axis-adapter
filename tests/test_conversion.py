import uuid
from pathlib import Path

import pytest
from visionapi.common_pb2 import MessageType
from visionapi.sae_pb2 import SaeMessage

from axisadapter.axisadapter import AxisAdapter
from axisadapter.config import (AxisAdapterConfig, ClassMapping, MqttConfig,
                                RedisConfig)

SAMPLE_PAYLOAD = (Path(__file__).parent / 'data' / 'single.jsonl').read_bytes()


@pytest.fixture
def adapter():
    config = AxisAdapterConfig(
        log_level='WARNING',
        redis=RedisConfig(stream_id='cam1'),
        mqtt=MqttConfig(topic='axis/detections'),
        class_mapping={'Car': ClassMapping(id=2, name='car')},
    )
    return AxisAdapter(config)

def _parse(adapter, payload) -> SaeMessage:
    out = adapter.get(payload)
    assert out is not None
    sae_msg = SaeMessage()
    sae_msg.ParseFromString(out)
    return sae_msg

def test_frame_metadata(adapter):
    sae_msg = _parse(adapter, SAMPLE_PAYLOAD)
    assert sae_msg.type == MessageType.SAE
    assert sae_msg.frame.source_id == 'cam1'
    assert sae_msg.frame.timestamp_utc_ms == 1784899130390

def test_unclassified_detections_are_dropped(adapter):
    # The sample has 4 detections, only 2 carry a class.
    sae_msg = _parse(adapter, SAMPLE_PAYLOAD)
    assert len(sae_msg.detections) == 2

def test_detection_fields(adapter):
    sae_msg = _parse(adapter, SAMPLE_PAYLOAD)

    det = next(d for d in sae_msg.detections
               if d.object_id == uuid.UUID('a48ac5f4-31df-42db-af35-0749555dfcf1').bytes)

    assert det.class_id == 2
    assert det.confidence == pytest.approx(0.85)
    assert det.bounding_box.min_x == pytest.approx(0.5128)
    assert det.bounding_box.min_y == pytest.approx(0.4274)
    assert det.bounding_box.max_x == pytest.approx(0.6185)
    assert det.bounding_box.max_y == pytest.approx(0.5045)

def test_class_names_populated(adapter):
    sae_msg = _parse(adapter, SAMPLE_PAYLOAD)
    assert dict(sae_msg.model_metadata.class_names) == {2: 'car'}

def test_unmapped_type_is_dropped():
    config = AxisAdapterConfig(
        log_level='WARNING',
        redis=RedisConfig(stream_id='cam1'),
        mqtt=MqttConfig(topic='axis/detections'),
        class_mapping={},  # 'Car' not mapped
    )
    sae_msg = _parse(AxisAdapter(config), SAMPLE_PAYLOAD)
    assert len(sae_msg.detections) == 0

def test_malformed_json_returns_none(adapter):
    assert adapter.get(b'not json') is None
