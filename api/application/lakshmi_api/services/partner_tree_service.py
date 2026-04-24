from application.lakshmi_api.models import PartnerTree
from sqlalchemy import insert, text
import global_resources


class PartnerTreeService:

    def __init__(self):
        self.db_orm = global_resources.db_orm
        self.logger = global_resources.logger

    async def add_parent_partner(self, child_id, parent_id):
        with self.db_orm.sessionmaker() as session:
            partner_tree = PartnerTree(parent=child_id, child=child_id, distance=0)
            session.add(partner_tree)
            session.commit()
        await self.add_ancestors(child_id, parent_id)

    async def add_ancestors(self, child_id, parent_id):
        with self.db_orm.sessionmaker() as session:
            ancestors = session.query(PartnerTree).filter(PartnerTree.child == parent_id).all()
            data = []
            for ancestor in ancestors:
                data.append({'parent': ancestor.parent, 'child': child_id, 'distance': ancestor.distance + 1})
            session.execute(insert(PartnerTree).values(data))
            session.commit()

    async def self_and_descendants(self, parent_id):
        query = '''
            SELECT partner.id
            FROM partner_tree
            INNER JOIN partner ON partner.id = partner_tree.child
            WHERE partner_tree.parent = :parent_id
        '''

        with self.db_orm.sessionmaker() as session:
            result = session.execute(text(query), {'parent_id': parent_id})
            return result.fetchall()

    async def descendants(self, parent_id):
        query = '''
            SELECT partner.id
            FROM partner_tree
            INNER JOIN partner ON partner.id = partner_tree.child
            WHERE partner_tree.parent = :parent_id AND partner.id != :parent_id
        '''

        with self.db_orm.sessionmaker() as session:
            result = session.execute(text(query), {'parent_id': parent_id})

            return result.fetchall()

    async def self_and_ancestors(self, child):
        query = '''
            SELECT partner.id
            FROM partner_tree
            INNER JOIN partner ON partner.id = partner_tree.parent
            WHERE partner_tree.child = :child
        '''

        with self.db_orm.sessionmaker() as session:
            result = session.execute(text(query), {'child': child})
            return result.fetchall()

    async def ancestors(self, child):
        query = '''
            SELECT partner.id
            FROM partner_tree
            INNER JOIN partner ON partner.id = partner_tree.parent
            WHERE partner_tree.child = :child AND partner.id != :child
        '''

        with self.db_orm.sessionmaker() as session:
            result = session.execute(text(query), {'child': child})

