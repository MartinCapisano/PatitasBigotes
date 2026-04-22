from pydantic import BaseModel, ConfigDict, Field


ADMIN_SCHEMA_CONFIG = ConfigDict(extra="forbid", str_strip_whitespace=True)
NAME_FIELD = Field(min_length=1, max_length=120)
OPTIONAL_NAME_FIELD = Field(default=None, min_length=1, max_length=120)
CATEGORY_FIELD = Field(min_length=1, max_length=80)
OPTIONAL_CATEGORY_FIELD = Field(default=None, min_length=1, max_length=80)
DESCRIPTION_FIELD = Field(default=None, max_length=1000)
IMG_URL_FIELD = Field(default=None, max_length=2048)
SKU_FIELD = Field(min_length=1, max_length=80)
OPTIONAL_SKU_FIELD = Field(default=None, min_length=1, max_length=80)
VARIANT_OPTION_FIELD = Field(default=None, min_length=1, max_length=80)


class CreateCategoryRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    name: str = CATEGORY_FIELD


class UpdateCategoryRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    name: str = CATEGORY_FIELD


class PatchCategoryRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    name: str | None = OPTIONAL_CATEGORY_FIELD


class CreateProductRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    name: str = NAME_FIELD
    description: str | None = DESCRIPTION_FIELD
    img_url: str | None = IMG_URL_FIELD
    category: str = CATEGORY_FIELD
    active: bool = True


class UpdateProductRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    name: str = NAME_FIELD
    description: str | None = DESCRIPTION_FIELD
    img_url: str | None = IMG_URL_FIELD
    category: str = CATEGORY_FIELD
    active: bool


class PatchProductRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    name: str | None = OPTIONAL_NAME_FIELD
    description: str | None = DESCRIPTION_FIELD
    img_url: str | None = IMG_URL_FIELD
    category: str | None = OPTIONAL_CATEGORY_FIELD
    active: bool | None = None


class CreateVariantRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    product_id: int = Field(gt=0)
    sku: str = SKU_FIELD
    size: str | None = VARIANT_OPTION_FIELD
    color: str | None = VARIANT_OPTION_FIELD
    img_url: str | None = IMG_URL_FIELD
    price: int = Field(gt=0)
    stock: int = Field(default=0, ge=0)
    active: bool = True


class UpdateVariantRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    product_id: int = Field(gt=0)
    sku: str = SKU_FIELD
    size: str | None = VARIANT_OPTION_FIELD
    color: str | None = VARIANT_OPTION_FIELD
    img_url: str | None = IMG_URL_FIELD
    price: int = Field(gt=0)
    stock: int = Field(ge=0)
    active: bool


class PatchVariantRequest(BaseModel):
    model_config = ADMIN_SCHEMA_CONFIG
    product_id: int | None = Field(default=None, gt=0)
    sku: str | None = OPTIONAL_SKU_FIELD
    size: str | None = VARIANT_OPTION_FIELD
    color: str | None = VARIANT_OPTION_FIELD
    img_url: str | None = IMG_URL_FIELD
    price: int | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    active: bool | None = None
