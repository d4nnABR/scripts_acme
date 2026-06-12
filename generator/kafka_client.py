import os
import json
from confluent_kafka import SerializingProducer
from confluent_kafka.serialization import StringSerializer, SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.json_schema import JSONSerializer
from confluent_kafka import Producer

TOPIC_GPS    = "acme-ev-gps-events"
TOPIC_STATUS = "acme-ev-status-events"
TOPIC_DLQ    = "acme-ev-dead-letter"

GPS_SCHEMA_STR = """
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AcmeEvGpsEvent",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "id_vehiculo":  { "type": "string" },
    "timestamp":    { "type": "string", "format": "date-time" },
    "tipo_trama":   { "type": "string", "enum": ["GPS"] },
    "telemetria": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "latitud":  { "type": "number", "minimum": -90,  "maximum": 90 },
        "longitud": { "type": "number", "minimum": -180, "maximum": 180 }
      },
      "required": ["latitud", "longitud"]
    }
  },
  "required": ["id_vehiculo", "timestamp", "tipo_trama", "telemetria"]
}
"""

STATUS_SCHEMA_STR = """
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AcmeEvStatusEvent",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "id_vehiculo":        { "type": "string" },
    "timestamp":          { "type": "string", "format": "date-time" },
    "tipo_trama":         { "type": "string", "enum": ["ESTADO"] },
    "reconexion":         { "type": "boolean" },
    "offline_desde":      { "type": "string", "format": "date-time" },
    "offline_hasta":      { "type": "string", "format": "date-time" },
    "tramas_buffereadas": { "type": "integer", "minimum": 0 },
    "telemetria": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "estado_carga":  { "type": "integer", "minimum": 0, "maximum": 100 },
        "on_off":        { "type": "integer", "enum": [0, 1] },
        "codigo_falla":  { "type": "integer", "minimum": 0, "maximum": 999 },
        "kilometros":    { "type": "integer", "minimum": 0 }
      },
      "required": ["estado_carga", "on_off", "codigo_falla", "kilometros"]
    }
  },
  "required": ["id_vehiculo", "timestamp", "tipo_trama", "telemetria"]
}
"""

def _base_producer_config() -> dict:
    return {
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVER"),
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms":   "PLAIN",
        "sasl.username":     os.getenv("KAFKA_API_KEY"),
        "sasl.password":     os.getenv("KAFKA_API_SECRET"),
    }

def crear_schema_registry_client() -> SchemaRegistryClient:
    return SchemaRegistryClient({
        "url": os.getenv("SCHEMA_REGISTRY_URL"),
        "basic.auth.user.info": f"{os.getenv('SCHEMA_REGISTRY_API_KEY')}:{os.getenv('SCHEMA_REGISTRY_API_SECRET')}",
    })

def crear_producer_gps(sr_client: SchemaRegistryClient) -> SerializingProducer:
    serializer = JSONSerializer(GPS_SCHEMA_STR, sr_client, conf={"auto.register.schemas": False, "use.latest.version": True})
    cfg = _base_producer_config()
    cfg["key.serializer"]   = StringSerializer("utf_8")
    cfg["value.serializer"] = serializer
    return SerializingProducer(cfg)

def crear_producer_status(sr_client: SchemaRegistryClient) -> SerializingProducer:
    serializer = JSONSerializer(STATUS_SCHEMA_STR, sr_client, conf={"auto.register.schemas": False, "use.latest.version": True})
    cfg = _base_producer_config()
    cfg["key.serializer"]   = StringSerializer("utf_8")
    cfg["value.serializer"] = serializer
    return SerializingProducer(cfg)

def crear_producer_dlq() -> Producer:
    return Producer(_base_producer_config())

def hacer_delivery_report(dlq_producer: Producer, topic_origen: str, id_vehiculo: str, payload: dict):
    def _report(err, msg):
        if err is not None:
            print(f"[ERROR] {id_vehiculo} → {topic_origen}: {err}")
            dlq_producer.produce(
                TOPIC_DLQ,
                key=id_vehiculo.encode(),
                value=json.dumps({
                    "timestamp":    payload.get("timestamp", ""),
                    "id_vehiculo":  id_vehiculo,
                    "topic_origen": topic_origen,
                    "motivo":       str(err),
                    "payload_raw":  json.dumps(payload),
                }).encode(),
            )
            dlq_producer.poll(0)
    return _report
