def calculate_offset(per_page, current_page):
    return (current_page - 1) * per_page


class PaginationService:

    def __init__(self, base_url, request):
        self.base_url = base_url
        self.request = request

    def set_default_value(self, key, default_value):
        value = self.request.arguments.get(key)
        if value is not None:
            value = value[0].decode()
        return int(value) if (value and value.isdigit()) else default_value

    def calculate_pagination_params(self):
        per_page = self.set_default_value("perPage", 100)
        current_page = self.set_default_value("currentPage", 1)

        return calculate_offset(per_page, current_page), per_page

    def _construct_pagination_data(self, total_count, per_page, current_page):
        total_pages = (total_count + per_page - 1) // per_page

        return {
            'total_pages': total_pages,
            'current_page': current_page,
            'next_page': self._construct_page_url(per_page, current_page + 1 if current_page < total_pages else None),
            'prev_page': self._construct_page_url(per_page, current_page - 1 if current_page > 1 else None)
        }

    async def calculate_pagination(self, total_count, per_page, current_page):
        pagination_data = self._construct_pagination_data(total_count, per_page, current_page)

        return calculate_offset(per_page, current_page), pagination_data

    def _construct_page_url(self, per_page, current_page):
        if current_page is None:
            return None
        else:
            args = dict(self.request.arguments)
            args = {k: v[0].decode() for k, v in args.items()}
            args.update({
                'perPage': str(per_page),
                'currentPage': str(current_page)
            })
            url = f"{self.base_url}?{'&'.join(f'{k}={v}' for k, v in args.items())}"
            return url

    async def get_pagination_data(self, total_count):
        offset, limit = self.calculate_pagination_params()
        offset, pagination_data = await self.calculate_pagination(total_count, limit, offset // limit + 1)
        return offset, limit, pagination_data
