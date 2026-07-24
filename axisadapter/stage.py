import logging
import signal
import threading

import paho.mqtt.client as mqtt
from prometheus_client import Counter, Histogram, start_http_server
from visionlib.pipeline import ValkeyPublisher

from .config import AxisAdapterConfig
from .axisadapter import AxisAdapter

logger = logging.getLogger(__name__)

REDIS_PUBLISH_DURATION = Histogram('axis_adapter_redis_publish_duration', 'The time it takes to push a message onto the Redis stream',
                                   buckets=(0.0025, 0.005, 0.0075, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25))
FRAME_COUNTER = Counter('axis_adapter_frame_counter', 'How many messages have been consumed from the MQTT broker')

def run_stage():

    stop_event = threading.Event()

    # Register signal handlers
    def sig_handler(signum, _):
        signame = signal.Signals(signum).name
        print(f'Caught signal {signame} ({signum}). Exiting...')
        stop_event.set()

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    # Load config from settings.yaml / env vars
    CONFIG = AxisAdapterConfig()

    logger.setLevel(CONFIG.log_level.value)

    logger.info(f'Starting prometheus metrics endpoint on port {CONFIG.prometheus_port}')

    start_http_server(CONFIG.prometheus_port)

    logger.info(f'Starting AXIS adapter stage. Config: {CONFIG.model_dump_json(indent=2)}')

    axis_adapter = AxisAdapter(CONFIG)

    output_stream_key = f'{CONFIG.redis.output_stream_prefix}:{CONFIG.redis.stream_id}'

    publish_ctx = ValkeyPublisher(CONFIG.redis.host, CONFIG.redis.port)

    with publish_ctx as publish:

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code != 0:
                logger.error(f'Failed to connect to MQTT broker: {reason_code}')
                return
            logger.info(f'Connected to MQTT broker, subscribing to topic "{CONFIG.mqtt.topic}"')
            client.subscribe(CONFIG.mqtt.topic, CONFIG.mqtt.qos)

        def on_message(client, userdata, msg):
            try:
                FRAME_COUNTER.inc()
                output_proto_data = axis_adapter.get(msg.payload)
                if output_proto_data is None:
                    return
                with REDIS_PUBLISH_DURATION.time():
                    publish(output_stream_key, output_proto_data)
            except Exception:
                logger.exception('Error while processing MQTT message')

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CONFIG.mqtt.client_id)
        client.on_connect = on_connect
        client.on_message = on_message

        if CONFIG.mqtt.username is not None:
            client.username_pw_set(CONFIG.mqtt.username, CONFIG.mqtt.password)

        if CONFIG.mqtt.tls is not None and CONFIG.mqtt.tls.enabled:
            client.tls_set(ca_certs=CONFIG.mqtt.tls.ca_certs,
                           certfile=CONFIG.mqtt.tls.certfile,
                           keyfile=CONFIG.mqtt.tls.keyfile)
            if CONFIG.mqtt.tls.insecure:
                client.tls_insecure_set(True)

        client.connect(CONFIG.mqtt.host, CONFIG.mqtt.port, CONFIG.mqtt.keepalive)
        client.loop_start()

        try:
            stop_event.wait()
        finally:
            client.loop_stop()
            client.disconnect()
