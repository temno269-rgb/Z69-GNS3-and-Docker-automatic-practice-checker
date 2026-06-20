import os
import time
import uuid

import yaml


class ComposeRuntime:
    """Изолированный запуск Compose v1/v2 с последующей проверкой через Docker API."""

    FILE_NAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")

    def __init__(self, checker, lab_name):
        self.checker = checker
        self.file_name = next(
            (name for name in self.FILE_NAMES
             if os.path.isfile(os.path.join(checker.project_dir, name))),
            None,
        )
        self.command = checker.get_compose_command()
        self.project = f"{lab_name}_{uuid.uuid4().hex[:10]}".lower()
        self.started = False

        if self.file_name:
            checker.active_compose_file = self.file_name
            checker.active_compose_project = self.project

    @property
    def available(self):
        return bool(self.file_name and self.command)

    @property
    def base_command(self):
        return self.command + ["-p", self.project, "-f", self.file_name]

    def config(self):
        if not self.available:
            return False, {}, "Compose-файл или команда Docker Compose не найдены"
        code, stdout, stderr = self.checker.run_subprocess(
            self.base_command + ["config"], timeout=30
        )
        if code != 0:
            return False, {}, stderr or stdout
        try:
            return True, yaml.safe_load(stdout) or {}, ""
        except yaml.YAMLError as exc:
            return False, {}, f"Compose вывел некорректный YAML: {exc}"

    def up(self, build=True):
        args = self.base_command + ["up", "-d"]
        if build:
            args.append("--build")
        code, stdout, stderr = self.checker.run_subprocess(args, timeout=240)
        self.started = code == 0
        return code == 0, stderr or stdout

    def containers(self, include_stopped=True):
        if not self.available:
            return []
        args = self.base_command + ["ps", "-q"]
        if include_stopped:
            args.append("-a")
        code, stdout, _ = self.checker.run_subprocess(args, timeout=20)
        if code != 0:
            return []
        result = []
        for container_id in stdout.splitlines():
            try:
                result.append(self.checker.client.containers.get(container_id.strip()))
            except Exception:
                continue
        return result

    @staticmethod
    def service_name(container):
        return container.labels.get("com.docker.compose.service", "")

    @staticmethod
    def published_ports(container, private_port=None):
        try:
            container.reload()
        except Exception:
            return []
        bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        result = []
        for internal, published in bindings.items():
            internal_number = int(internal.split("/", 1)[0])
            if private_port is not None and internal_number != private_port:
                continue
            for binding in published or []:
                if binding.get("HostPort"):
                    result.append(int(binding["HostPort"]))
        return sorted(set(result))

    def wait_for_containers(self, minimum, timeout=15):
        deadline = time.monotonic() + timeout
        last = []
        while time.monotonic() < deadline:
            last = self.containers()
            if len(last) >= minimum:
                for container in last:
                    try:
                        container.reload()
                    except Exception:
                        pass
                if all(container.status == "running" for container in last):
                    return last
                if any(container.status in ("exited", "dead") for container in last):
                    return last
            time.sleep(0.25)
        return last

    def down(self):
        if not self.available:
            return False, "Docker Compose недоступен"
        code, stdout, stderr = self.checker.run_subprocess(
            self.base_command + ["down", "--remove-orphans"], timeout=90
        )
        self.started = False
        return code == 0, stderr or stdout

    def project_resources_removed(self, container_ids):
        for container_id in container_ids:
            try:
                self.checker.client.containers.get(container_id)
                return False
            except Exception:
                pass
        try:
            networks = self.checker.client.networks.list(
                filters={"label": f"com.docker.compose.project={self.project}"}
            )
            return not networks
        except Exception:
            return True
