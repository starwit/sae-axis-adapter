import os
from typing import Dict, Optional

from pydantic import BaseModel, Field
from pydantic_settings import (BaseSettings, SettingsConfigDict,
                               YamlConfigSettingsSource)
from typing_extensions import Annotated
from visionlib.pipeline.settings import LogLevel


class RedisConfig(BaseModel):
    host: str = 'localhost'
    port: Annotated[int, Field(ge=1, le=65536)] = 6379
    stream_id: str
    output_stream_prefix: str = 'axisadapter'

class MqttTlsConfig(BaseModel):
    enabled: bool = True
    ca_certs: Optional[str] = None
    certfile: Optional[str] = None
    keyfile: Optional[str] = None
    insecure: bool = False

class MqttConfig(BaseModel):
    host: str = 'localhost'
    port: Annotated[int, Field(ge=1, le=65536)] = 1883
    topic: str
    keepalive: Annotated[int, Field(ge=1)] = 60
    qos: Annotated[int, Field(ge=0, le=2)] = 0
    client_id: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    tls: Optional[MqttTlsConfig] = None

class ClassMapping(BaseModel):
    id: Annotated[int, Field(ge=0)]
    name: str

class FrameShapeConfig(BaseModel):
    height: Annotated[int, Field(ge=1)]
    width: Annotated[int, Field(ge=1)]
    channels: Annotated[int, Field(ge=1)] = 3

class AxisAdapterConfig(BaseSettings):
    log_level: LogLevel = LogLevel.WARNING
    redis: RedisConfig
    mqtt: MqttConfig
    frame_shape: FrameShapeConfig
    class_mapping: Dict[str, ClassMapping] = {}
    prometheus_port: Annotated[int, Field(ge=1024, le=65536)] = 8000

    model_config = SettingsConfigDict(env_nested_delimiter='__')

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        YAML_LOCATION = os.environ.get('SETTINGS_FILE', 'settings.yaml')
        return (init_settings, env_settings, YamlConfigSettingsSource(settings_cls, yaml_file=YAML_LOCATION), file_secret_settings)
