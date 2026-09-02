from __future__ import annotations

import httpx


class HomeAssistantClient:
    def __init__(self, url: str | None, token: str | None, allowed: frozenset[str]):
        self.url = url
        self.token = token
        self.allowed = allowed

    def _validate(self, entity_id: str) -> None:
        if not self.url or not self.token:
            raise RuntimeError("Home Assistant nao configurado.")
        if entity_id not in self.allowed:
            raise PermissionError(f"Entidade nao permitida: {entity_id}")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def get_state(self, entity_id: str) -> dict:
        self._validate(entity_id)
        response = httpx.get(
            f"{self.url}/api/states/{entity_id}", headers=self._headers, timeout=10
        )
        response.raise_for_status()
        return response.json()

    def set_power(self, entity_id: str, turn_on: bool) -> dict:
        self._validate(entity_id)
        domain = entity_id.split(".", 1)[0]
        if domain not in {"light", "switch"}:
            raise PermissionError(f"Dominio nao controlavel no MVP: {domain}")
        service = "turn_on" if turn_on else "turn_off"
        response = httpx.post(
            f"{self.url}/api/services/{domain}/{service}",
            headers=self._headers,
            json={"entity_id": entity_id},
            timeout=10,
        )
        response.raise_for_status()
        return {"status": "ok", "entity_id": entity_id, "action": service}
