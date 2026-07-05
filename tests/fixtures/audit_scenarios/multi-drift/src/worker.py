import boto3
import redis

ddb = boto3.client("dynamodb")
cache = redis.Redis(host="localhost")
mcp.connect("payments-mcp")
