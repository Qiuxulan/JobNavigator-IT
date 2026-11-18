import Taro from '@tarojs/taro'

const USER_ID_KEY = 'jobnav_user_id'

function uuid(): string {
  // 简易 uuid v4，足够作为本地持久用户标识
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/** 获取（必要时生成并持久化）本地 user_id。 */
export function getUserId(): string {
  try {
    let id = Taro.getStorageSync(USER_ID_KEY)
    if (!id || typeof id !== 'string') {
      id = uuid()
      Taro.setStorageSync(USER_ID_KEY, id)
    }
    return id
  } catch (e) {
    return uuid()
  }
}
