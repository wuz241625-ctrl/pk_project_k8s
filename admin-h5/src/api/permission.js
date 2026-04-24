import request from '@/utils/request'

export function getPermissions() {
  return request({
    url: '/role/getpermissions',
    method: 'post'
  })
}

export function getCurrentUserRolePermissions() {
    return request({
        url: '/role/getCurrentUserRolePermissions',
        method: 'post'
    })
}

export function getRoles(data) {
  return request({
    url: '/role/getrole',
    method: 'post',
    data
  })
}

export function getCurrentUserRole(data) {
  return request({
    url: '/role/getCurrentUserRole',
    method: 'post',
    data
  })
}


export function getRight(data) {
  return request({
    url: '/role/getright',
    method: 'post',
    data
  })
}


export function addRight(data) {
  return request({
    url: '/role/addright',
    method: 'post',
    data
  })
}

export function updateRight(data) {
  return request({
    url: `/role/updateright`,
    method: 'post',
    data
  })
}

export function deleteRight(data) {
  return request({
    url: `/role/deleteright`,
    method: 'post',
    data
  })
}


export function addRole(data) {
  return request({
    url: '/role/addrole',
    method: 'post',
    data
  })
}

export function updateRole(data) {
  return request({
    url: `/role/updaterole`,
    method: 'post',
    data
  })
}

export function deleteRole(data) {
  return request({
    url: `/role/deleterole`,
    method: 'post',
    data
  })
}

export function getMembers(data) {
  return request({
    url: '/member/getmember',
    method: 'post',
    data
  })
}

export function addMember(data) {
  return request({
    url: '/member/addmember',
    method: 'post',
    data
  })
}

export function updateMember(data) {
  return request({
    url: `/member/updatemember`,
    method: 'post',
    data
  })
}

export function deleteMember(data) {
  return request({
    url: `/member/deletemember`,
    method: 'post',
    data
  })
}

export function resetGgkey(data) {
  return request({
    url: `/member/resetggkey`,
    method: 'post',
    data
  })
}
