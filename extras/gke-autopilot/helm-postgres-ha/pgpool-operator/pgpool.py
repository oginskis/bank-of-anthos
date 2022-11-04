import asyncio
import datetime
import logging
import kopf
from kubernetes import client
from kubernetes.client.rest import ApiException

LOCK: asyncio.Lock


@kopf.on.startup()
async def startup(**_):
    """
    uses the running asyncio loop by default
    """
    global LOCK
    LOCK = asyncio.Lock()


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.posting.level = logging.WARNING
    settings.watching.connect_timeout = 1 * 60
    settings.watching.server_timeout = 10 * 60


@kopf.on.probe(id='now')
def get_current_timestamp(**kwargs):
    return datetime.datetime.utcnow().isoformat()


@kopf.on.login()
def login(**kwargs):
    global api

    conn = kopf.login_via_client(**kwargs)
    api = client.AppsV1Api()
    return conn


@kopf.on.update(kind="StatefulSet",
                labels={
                    "app.kubernetes.io/component": "postgresql",
                    "app.kubernetes.io/instance": "accounts-db"
                })
def update_pgpool_deployment(logger, new, old, **kwargs):
    if new['spec']['replicas'] != old['spec']['replicas']:
        pgpoolBackEndNodes = ""
        for i in range(new['spec']['replicas']):
            pgpoolBackEndNodes += f"{i}:accounts-db-postgresql-{i}.accounts-db-postgresql-headless:5432,"

        try:
            pgpoolDeployment = api.read_namespaced_deployment(
                name="accounts-db-pgpool", namespace="default")

            def map_envvar(envvar):
                if envvar.name == "PGPOOL_BACKEND_NODES":
                    envvar.value = pgpoolBackEndNodes

                return envvar

            def map_containers(container):
                if container.name == "pgpool":
                    container.env = list(map(map_envvar, container.env))

                return container

            pgpoolDeployment.spec.template.spec.containers = list(
                map(
                    map_containers,
                    pgpoolDeployment.spec.template.spec.containers
                )
            )

            api.patch_namespaced_deployment(
                name="accounts-db-pgpool",
                namespace="default",
                body=pgpoolDeployment
            )
            logger.info("PGPool deployment updated")
        except ApiException as e:
            logger.error("Exception when calling AppsV1Api: %s\n" % e)
    pass
