const getters = {
  visitedViews: state => state.tagsView.visitedViews,
  cachedViews: state => state.tagsView.cachedViews,
  device: state => state.app.device,
  size: state => state.app.size,
  sidebar: state => state.app.sidebar,
  token: state => state.user.token,
  id: state => state.user.id,
  name: state => state.user.name,
  permission_routes: state => state.permission.routes
}
export default getters
