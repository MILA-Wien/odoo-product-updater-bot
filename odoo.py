import xmlrpc.client

ODOO = {
    "BASE_URL": "https://erp.supercoop.de/",
    "DATABASE": "odoo",
    "USERNAME": "product-updater-bot",
    "PASSWORD": "",
}


class OdooAPI:
    """Class to handle Odoo API requests."""

    # Singleton instance
    _connection = None

    _common = None
    _uid = None
    _models = None

    @classmethod
    def get_connection(cls):
        if cls._connection == None:
            cls._connection = __class__(
                ODOO["BASE_URL"],
                ODOO["DATABASE"],
                ODOO["USERNAME"],
                ODOO["PASSWORD"],
            )
        return cls._connection

    def __init__(self, base_url, db, user, password):
        """Initialize xmlrpc connection."""
        self._db = db
        self._username = user
        self._password = password

        self._common = xmlrpc.client.ServerProxy("{}xmlrpc/2/common".format(base_url))
        self._uid = self._common.authenticate(
            self._db, self._username, self._password, {}
        )
        self._models = xmlrpc.client.ServerProxy("{}xmlrpc/2/object".format(base_url))

    def fields_get(self, entity):
        fields = self._models.execute_kw(
            self._db,
            self._uid,
            self._password,
            entity,
            "fields_get",
            [],
            {"attributes": ["string", "help", "type"]},
        )
        return fields

    def search_count(self, entity, cond=[]):
        return self._models.execute_kw(
            self._db, self._uid, self._password, entity, "search_count", [cond]
        )

    def search_read(
        self, entity, cond=[], fields=[], limit=3500, offset=0, order="id ASC"
    ):
        fields_and_context = {
            "fields": fields,
            "limit": limit,
            "offset": offset,
            "order": order,
        }
        return self._models.execute_kw(
            self._db,
            self._uid,
            self._password,
            entity,
            "search_read",
            [cond],
            fields_and_context,
        )

    def get(self, entity, cond=[], fields=[]):
        r = self.search_read(entity, cond=cond, fields=fields)
        if len(r) > 0:
            return r[0]

    def write(self, entity, ids, fields):
        return self._models.execute_kw(
            self._db, self._uid, self._password, entity, "write", [ids, fields]
        )

    def unlink(self, entity, ids):
        return self._models.execute_kw(
            self._db, self._uid, self._password, entity, "unlink", [ids]
        )

    def create(self, entity, fields):
        return self._models.execute_kw(
            self._db, self._uid, self._password, entity, "create", [fields]
        )

    def execute(self, entity, method, ids, params={}):
        return self._models.execute_kw(
            self._db, self._uid, self._password, entity, method, [ids], params
        )


if __name__ == "__main__":
    c = OdooAPI.get_connection()
