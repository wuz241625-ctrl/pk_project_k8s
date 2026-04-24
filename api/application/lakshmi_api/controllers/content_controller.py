from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.schema.text_material_schema import TextMaterialSchema
from application.lakshmi_api.models.text_material import TextMaterial


class TextMaterials(BaseHandler):
    @handle_errors
    async def get(self):
        genre = self.get_query_argument('type')
        text_materials = await self._get_text_material_by_genre(genre)
        self.write({"data": text_materials})

    async def _get_text_material_by_genre(self, genre):
        with self.db_orm.sessionmaker() as session:
            text_materials = session.query(TextMaterial).filter_by(genre=genre).first()
        if text_materials is None:
            raise ApiError('Content not found')
        return TextMaterialSchema().dump(text_materials)
