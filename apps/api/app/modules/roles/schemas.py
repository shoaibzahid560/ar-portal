from pydantic import BaseModel, ConfigDict


class PermissionOut(BaseModel):
    key: str
    module: str
    description: str


class RoleOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    permissions: list[str]


class RolesResponse(BaseModel):
    roles: list[RoleOut]
    permissions: list[PermissionOut]


class PermissionKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: list[str]
