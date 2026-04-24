// build.js
const { execSync } = require('child_process')
const config = require('./build.config')

// 获取命令参数
const system = process.argv[2]
const env = process.argv[3]

if (!system || !env) {
  console.error('❌ 请传入参数，例如：node build.js system1 dev')
  process.exit(1)
}

const vars = config?.[system]?.[env]

if (!vars) {
  console.error(`❌ 未找到配置：system=${system}, env=${env}`)
  process.exit(1)
}

// 拼接 cross-env 注入命令
const envString = Object.entries(Object.assign(vars, config?.[system].common))
  .map(([key, value]) => `${key}=${value}`)
  .join(' ')


if(['dev', 'development'].includes(env)){
    execSync(`npx cross-env ${envString} vue-cli-service serve`, {
        stdio: 'inherit',
    })
}else{
    execSync(`npx cross-env ${envString} vue-cli-service build`, {
        stdio: 'inherit',
    })
}

