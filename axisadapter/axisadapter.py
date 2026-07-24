import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from prometheus_client import Counter, Histogram, Summary
from visionapi.common_pb2 import MessageType
from visionapi.sae_pb2 import SaeMessage

from .config import AxisAdapterConfig

logging.basicConfig(format='%(asctime)s %(name)-15s %(levelname)-8s %(processName)-10s %(message)s')
logger = logging.getLogger(__name__)

GET_DURATION = Histogram('axis_adapter_get_duration', 'The time it takes to parse the AXIS JSON payload until returning the serialized SAE proto',
                         buckets=(0.0025, 0.005, 0.0075, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25))
OBJECT_COUNTER = Counter('axis_adapter_object_counter', 'How many detections have been transformed')
PROTO_SERIALIZATION_DURATION = Summary('axis_adapter_proto_serialization_duration', 'The time it takes to create a serialized output proto')


class AxisAdapter:
    def __init__(self, config: AxisAdapterConfig) -> None:
        self.config = config
        logger.setLevel(self.config.log_level.value)

    def __call__(self, payload) -> Any:
        return self.get(payload)

    @GET_DURATION.time()
    def get(self, payload) -> Optional[bytes]:
        axis_msg = self._parse_axis_json(payload)
        if axis_msg is None:
            return None

        sae_msg = self._build_sae_message(axis_msg)

        return self._pack_proto(sae_msg)

    def _parse_axis_json(self, payload) -> Optional[dict]:
        try:
            return json.loads(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f'Could not parse AXIS JSON payload, discarding message: {e}')
            return None

    def _build_sae_message(self, axis_msg: dict) -> SaeMessage:
        sae_msg = SaeMessage()
        sae_msg.type = MessageType.SAE
        sae_msg.frame.source_id = self.config.redis.stream_id
        sae_msg.frame.shape.height = self.config.frame_shape.height
        sae_msg.frame.shape.width = self.config.frame_shape.width
        sae_msg.frame.shape.channels = self.config.frame_shape.channels

        timestamp = axis_msg.get('timestamp')
        timestamp_ms = self._parse_timestamp_ms(timestamp)
        if timestamp_ms is not None:
            sae_msg.frame.timestamp_utc_ms = timestamp_ms

        used_classes: dict[int, str] = {}

        for detection in axis_msg.get('detections', []):
            axis_class = detection.get('class')
            if axis_class is None:
                # AXIS reports objects before they are classified; discard those.
                continue

            axis_type = axis_class.get('type')
            mapping = self.config.class_mapping.get(axis_type)
            if mapping is None:
                logger.warning(f'No class mapping configured for AXIS type "{axis_type}", discarding detection')
                continue

            object_id = self._parse_object_id(detection.get('object_track_id'))
            if object_id is None:
                continue

            sae_detection = sae_msg.detections.add()
            sae_detection.class_id = mapping.id
            sae_detection.confidence = axis_class.get('score', 0.0)
            sae_detection.object_id = object_id

            bbox = detection.get('bounding_box', {})
            sae_detection.bounding_box.min_x = bbox.get('left', 0.0)
            sae_detection.bounding_box.min_y = bbox.get('top', 0.0)
            sae_detection.bounding_box.max_x = bbox.get('right', 0.0)
            sae_detection.bounding_box.max_y = bbox.get('bottom', 0.0)

            used_classes[mapping.id] = mapping.name
            OBJECT_COUNTER.inc()

        for class_id, class_name in used_classes.items():
            sae_msg.model_metadata.class_names[class_id] = class_name

        return sae_msg

    def _parse_timestamp_ms(self, timestamp) -> Optional[int]:
        if timestamp is None:
            return None
        try:
            return int(datetime.fromisoformat(timestamp).timestamp() * 1000)
        except (ValueError, TypeError) as e:
            logger.warning(f'Could not parse timestamp "{timestamp}": {e}')
            return None

    def _parse_object_id(self, object_track_id) -> Optional[bytes]:
        if object_track_id is None:
            logger.warning('Detection is missing object_track_id, discarding detection')
            return None
        try:
            return uuid.UUID(object_track_id).bytes
        except (ValueError, AttributeError) as e:
            logger.warning(f'Could not parse object_track_id "{object_track_id}": {e}')
            return None

    @PROTO_SERIALIZATION_DURATION.time()
    def _pack_proto(self, sae_msg: SaeMessage) -> bytes:
        return sae_msg.SerializeToString()
