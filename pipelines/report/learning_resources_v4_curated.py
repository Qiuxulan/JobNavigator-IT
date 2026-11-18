# -*- coding: utf-8 -*-
"""learning_resources_v4 人工整理资源表（curated tables）。

所有 URL 均为公开知名资源的稳定落地页（官方文档、知名免费课程、知名 UP 主/频道），
由管道运行时逐一验证可达性（结果缓存到 raw/courses/_linkcheck/），验证失败的条目
会被丢弃并记录在 QC 报告中。title 缺省时用技能名生成。

CURATED_DOCS: skill_id -> list of dicts:
    url, title, language('zh'/'en'), type, level, note(可选, 说明来源性质)
"""

# ---------------------------------------------------------------------------
# 官方文档 / 权威教程（中英文），按 skill_id 组织
# ---------------------------------------------------------------------------
CURATED_DOCS = {
    # ----- 编程语言 -----
    "python": [
        {"url": "https://docs.python.org/3/", "language": "en", "type": "doc", "level": "beginner", "title": "Python 官方文档"},
        {"url": "https://docs.python.org/zh-cn/3/", "language": "zh", "type": "doc", "level": "beginner", "title": "Python 官方文档（中文）"},
        {"url": "https://www.liaoxuefeng.com/wiki/1016959663602400", "language": "zh", "type": "tutorial", "level": "beginner", "title": "廖雪峰 Python3 教程"},
        {"url": "https://realpython.com/", "language": "en", "type": "tutorial", "level": "intermediate", "title": "Real Python 教程"},
    ],
    "java": [
        {"url": "https://docs.oracle.com/javase/tutorial/", "language": "en", "type": "doc", "level": "beginner", "title": "Oracle Java Tutorials（官方）"},
        {"url": "https://how2j.cn/", "language": "zh", "type": "interactive", "level": "beginner", "title": "How2J Java 全栈学习（中文）"},
    ],
    "javascript": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript", "language": "en", "type": "doc", "level": "beginner", "title": "MDN JavaScript 文档"},
        {"url": "https://developer.mozilla.org/zh-CN/docs/Web/JavaScript", "language": "zh", "type": "doc", "level": "beginner", "title": "MDN JavaScript 文档（中文）"},
        {"url": "https://javascript.info/", "language": "en", "type": "tutorial", "level": "beginner", "title": "The Modern JavaScript Tutorial"},
        {"url": "https://zh.javascript.info/", "language": "zh", "type": "tutorial", "level": "beginner", "title": "现代 JavaScript 教程（中文）"},
    ],
    "typescript": [
        {"url": "https://www.typescriptlang.org/docs/", "language": "en", "type": "doc", "level": "beginner", "title": "TypeScript 官方手册"},
        {"url": "https://typescript.bootcss.com/", "language": "zh", "type": "doc", "level": "beginner", "title": "TypeScript 中文手册"},
    ],
    "c": [
        {"url": "https://en.cppreference.com/w/c", "language": "en", "type": "doc", "level": "beginner", "title": "cppreference C 语言参考"},
        {"url": "https://zh.cppreference.com/w/c", "language": "zh", "type": "doc", "level": "beginner", "title": "cppreference C 语言参考（中文）"},
    ],
    "cpp": [
        {"url": "https://en.cppreference.com/w/", "language": "en", "type": "doc", "level": "beginner", "title": "cppreference C++ 参考"},
        {"url": "https://zh.cppreference.com/w/", "language": "zh", "type": "doc", "level": "beginner", "title": "cppreference C++ 参考（中文）"},
    ],
    "csharp": [
        {"url": "https://learn.microsoft.com/en-us/dotnet/csharp/", "language": "en", "type": "doc", "level": "beginner", "title": "Microsoft C# 文档（官方）"},
        {"url": "https://learn.microsoft.com/zh-cn/dotnet/csharp/", "language": "zh", "type": "doc", "level": "beginner", "title": "Microsoft C# 文档（官方中文）"},
    ],
    "go": [
        {"url": "https://go.dev/doc/", "language": "en", "type": "doc", "level": "beginner", "title": "Go 官方文档"},
        {"url": "https://golang.google.cn/doc/", "language": "zh", "type": "doc", "level": "beginner", "title": "Go 官方文档（中国镜像）"},
        {"url": "https://gopl-zh.github.io/", "language": "zh", "type": "book", "level": "intermediate", "title": "《Go 语言圣经》中文版"},
    ],
    "rust": [
        {"url": "https://doc.rust-lang.org/book/", "language": "en", "type": "book", "level": "beginner", "title": "The Rust Programming Language（官方入门书）"},
        {"url": "https://kaisery.github.io/trpl-zh-cn/", "language": "zh", "type": "book", "level": "beginner", "title": "Rust 程序设计语言（中文翻译）"},
    ],
    "ruby": [
        {"url": "https://ruby-doc.org/", "language": "en", "type": "doc", "level": "beginner", "title": "Ruby 官方文档"},
        {"url": "https://www.ruby-lang.org/zh_cn/documentation/", "language": "zh", "type": "doc", "level": "beginner", "title": "Ruby 官方文档（中文）"},
    ],
    "php": [
        {"url": "https://www.php.net/docs.php", "language": "en", "type": "doc", "level": "beginner", "title": "PHP 官方文档"},
        {"url": "https://www.php.net/manual/zh/", "language": "zh", "type": "doc", "level": "beginner", "title": "PHP 官方文档（中文）"},
    ],
    "swift": [
        {"url": "https://docs.swift.org/swift-book/", "language": "en", "type": "doc", "level": "beginner", "title": "The Swift Programming Language（官方）"},
    ],
    "kotlin": [
        {"url": "https://kotlinlang.org/docs/home.html", "language": "en", "type": "doc", "level": "beginner", "title": "Kotlin 官方文档"},
        {"url": "https://book.kotlincn.net/", "language": "zh", "type": "doc", "level": "beginner", "title": "Kotlin 中文文档"},
    ],
    "scala": [
        {"url": "https://docs.scala-lang.org/", "language": "en", "type": "doc", "level": "beginner", "title": "Scala 官方文档"},
    ],
    "r": [
        {"url": "https://cran.r-project.org/manuals.html", "language": "en", "type": "doc", "level": "beginner", "title": "R 官方手册（CRAN）"},
    ],
    "matlab": [
        {"url": "https://matlabacademy.mathworks.com/", "language": "en", "type": "doc", "level": "beginner", "title": "MATLAB Academy 官方免费入门课（原 help 文档被代理 403）"},
    ],
    "perl": [
        {"url": "https://perldoc.perl.org/", "language": "en", "type": "doc", "level": "beginner", "title": "Perl 官方文档（perldoc）"},
    ],
    "sql-lang": [
        {"url": "https://www.w3schools.com/sql/", "language": "en", "type": "tutorial", "level": "beginner", "title": "W3Schools SQL 教程"},
        {"url": "https://sqlbolt.com/", "language": "en", "type": "interactive", "level": "beginner", "title": "SQLBolt（交互式 SQL 练习）"},
    ],
    "solidity": [
        {"url": "https://docs.soliditylang.org/", "language": "en", "type": "doc", "level": "beginner", "title": "Solidity 官方文档"},
        {"url": "https://learnblockchain.cn/docs/solidity/", "language": "zh", "type": "doc", "level": "beginner", "title": "Solidity 中文文档（登链社区）"},
    ],
    "dart": [
        {"url": "https://dart.dev/guides", "language": "en", "type": "doc", "level": "beginner", "title": "Dart 官方文档"},
    ],
    "shell": [
        {"url": "https://www.gnu.org/software/bash/manual/", "language": "en", "type": "doc", "level": "beginner", "title": "Bash Reference Manual（GNU 官方）"},
        {"url": "https://man.linuxde.net/", "language": "zh", "type": "doc", "level": "beginner", "title": "Linux 命令大全（中文）"},
        {"url": "https://missing.csail.mit.edu/", "language": "en", "type": "course", "level": "beginner", "title": "MIT The Missing Semester（工具课：Shell/Git/编辑器）"},
    ],
    "powershell": [
        {"url": "https://learn.microsoft.com/en-us/powershell/", "language": "en", "type": "doc", "level": "beginner", "title": "Microsoft PowerShell 文档（官方）"},
        {"url": "https://learn.microsoft.com/zh-cn/powershell/", "language": "zh", "type": "doc", "level": "beginner", "title": "Microsoft PowerShell 文档（官方中文）"},
    ],
    # ----- 前端 -----
    "html": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/HTML", "language": "en", "type": "doc", "level": "beginner", "title": "MDN HTML 文档"},
        {"url": "https://developer.mozilla.org/zh-CN/docs/Web/HTML", "language": "zh", "type": "doc", "level": "beginner", "title": "MDN HTML 文档（中文）"},
        {"url": "https://developer.mozilla.org/en-US/docs/Learn", "language": "en", "type": "tutorial", "level": "beginner", "title": "MDN Learn Web Development"},
    ],
    "css": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/CSS", "language": "en", "type": "doc", "level": "beginner", "title": "MDN CSS 文档"},
        {"url": "https://developer.mozilla.org/zh-CN/docs/Web/CSS", "language": "zh", "type": "doc", "level": "beginner", "title": "MDN CSS 文档（中文）"},
        {"url": "https://web.dev/learn/css", "language": "en", "type": "tutorial", "level": "beginner", "title": "web.dev Learn CSS（Google）"},
    ],
    "html-css": [
        {"url": "https://developer.mozilla.org/en-US/docs/Learn", "language": "en", "type": "tutorial", "level": "beginner", "title": "MDN Learn Web Development"},
        {"url": "https://www.theodinproject.com/", "language": "en", "type": "course", "level": "beginner", "title": "The Odin Project（免费 Web 全栈课程）"},
    ],
    "react": [
        {"url": "https://react.dev/learn", "language": "en", "type": "doc", "level": "beginner", "title": "React 官方文档"},
        {"url": "https://zh-hans.react.dev/learn", "language": "zh", "type": "doc", "level": "beginner", "title": "React 官方文档（中文）"},
    ],
    "vue": [
        {"url": "https://vuejs.org/guide/introduction.html", "language": "en", "type": "doc", "level": "beginner", "title": "Vue.js 官方文档"},
        {"url": "https://cn.vuejs.org/guide/introduction.html", "language": "zh", "type": "doc", "level": "beginner", "title": "Vue.js 官方文档（中文）"},
    ],
    "angular": [
        {"url": "https://angular.dev/overview", "language": "en", "type": "doc", "level": "beginner", "title": "Angular 官方文档"},
        {"url": "https://angular.cn/", "language": "zh", "type": "doc", "level": "beginner", "title": "Angular 中文文档（社区）"},
    ],
    "svelte": [
        {"url": "https://svelte.dev/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Svelte 官方文档"},
    ],
    "nextjs": [
        {"url": "https://nextjs.org/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Next.js 官方文档"},
    ],
    "nuxt": [
        {"url": "https://nuxt.com/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Nuxt 官方文档"},
    ],
    "redux": [
        {"url": "https://redux.js.org/", "language": "en", "type": "doc", "level": "intermediate", "title": "Redux 官方文档"},
    ],
    "jquery": [
        {"url": "https://api.jquery.com/", "language": "en", "type": "doc", "level": "beginner", "title": "jQuery API 文档（官方）"},
    ],
    "tailwind": [
        {"url": "https://tailwindcss.com/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Tailwind CSS 官方文档"},
        {"url": "https://www.tailwindcss.cn/", "language": "zh", "type": "doc", "level": "beginner", "title": "Tailwind CSS 中文文档（社区）"},
    ],
    "bootstrap": [
        {"url": "https://getbootstrap.com/docs/5.3/getting-started/introduction/", "language": "en", "type": "doc", "level": "beginner", "title": "Bootstrap 官方文档"},
    ],
    "sass": [
        {"url": "https://sass-lang.com/documentation/", "language": "en", "type": "doc", "level": "beginner", "title": "Sass 官方文档"},
    ],
    "webpack": [
        {"url": "https://webpack.js.org/concepts/", "language": "en", "type": "doc", "level": "intermediate", "title": "Webpack 官方文档"},
        {"url": "https://webpack.docschina.org/concepts/", "language": "zh", "type": "doc", "level": "intermediate", "title": "Webpack 中文文档"},
    ],
    "vite": [
        {"url": "https://vite.dev/guide/", "language": "en", "type": "doc", "level": "beginner", "title": "Vite 官方文档"},
        {"url": "https://cn.vite.dev/guide/", "language": "zh", "type": "doc", "level": "beginner", "title": "Vite 中文文档"},
    ],
    "electron": [
        {"url": "https://www.electronjs.org/docs/latest", "language": "en", "type": "doc", "level": "intermediate", "title": "Electron 官方文档"},
    ],
    "threejs": [
        {"url": "https://threejs.org/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Three.js 官方文档"},
    ],
    "webgl": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API", "language": "en", "type": "doc", "level": "intermediate", "title": "MDN WebGL 文档"},
    ],
    "websocket": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/API/WebSocket", "language": "en", "type": "doc", "level": "intermediate", "title": "MDN WebSocket 文档"},
    ],
    # ----- 后端 -----
    "nodejs": [
        {"url": "https://nodejs.org/docs/latest/api/", "language": "en", "type": "doc", "level": "beginner", "title": "Node.js 官方 API 文档"},
        {"url": "https://nodejs.cn/api/", "language": "zh", "type": "doc", "level": "beginner", "title": "Node.js API 中文文档"},
    ],
    "express": [
        {"url": "https://expressjs.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Express 官方文档"},
    ],
    "nestjs": [
        {"url": "https://docs.nestjs.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "NestJS 官方文档"},
    ],
    "django": [
        {"url": "https://docs.djangoproject.com/en/stable/", "language": "en", "type": "doc", "level": "beginner", "title": "Django 官方文档"},
        {"url": "https://docs.djangoproject.com/zh-hans/stable/", "language": "zh", "type": "doc", "level": "beginner", "title": "Django 官方文档（中文）"},
    ],
    "flask": [
        {"url": "https://flask.palletsprojects.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Flask 官方文档"},
    ],
    "fastapi": [
        {"url": "https://fastapi.tiangolo.com/", "language": "en", "type": "doc", "level": "beginner", "title": "FastAPI 官方文档"},
        {"url": "https://fastapi.tiangolo.com/zh/", "language": "zh", "type": "doc", "level": "beginner", "title": "FastAPI 官方文档（中文）"},
    ],
    "spring": [
        {"url": "https://docs.spring.io/spring-framework/reference/", "language": "en", "type": "doc", "level": "intermediate", "title": "Spring Framework 官方文档"},
        {"url": "https://springdoc.cn/", "language": "zh", "type": "doc", "level": "intermediate", "title": "Spring 中文文档（社区）"},
    ],
    "springboot": [
        {"url": "https://docs.spring.io/spring-boot/index.html", "language": "en", "type": "doc", "level": "beginner", "title": "Spring Boot 官方文档"},
    ],
    "dotnet": [
        {"url": "https://learn.microsoft.com/en-us/dotnet/", "language": "en", "type": "doc", "level": "beginner", "title": "Microsoft .NET 文档（官方）"},
        {"url": "https://learn.microsoft.com/zh-cn/dotnet/", "language": "zh", "type": "doc", "level": "beginner", "title": "Microsoft .NET 文档（官方中文）"},
    ],
    "laravel": [
        {"url": "https://laravel.com/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Laravel 官方文档"},
    ],
    "symfony": [
        {"url": "https://symfony.com/doc/current/index.html", "language": "en", "type": "doc", "level": "intermediate", "title": "Symfony 官方文档"},
    ],
    "rails": [
        {"url": "https://guides.rubyonrails.org/", "language": "en", "type": "doc", "level": "beginner", "title": "Ruby on Rails Guides（官方）"},
    ],
    "gin": [
        {"url": "https://gin-gonic.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Gin Web Framework 官方文档"},
    ],
    "hibernate": [
        {"url": "https://hibernate.org/orm/documentation/", "language": "en", "type": "doc", "level": "intermediate", "title": "Hibernate 官方文档"},
    ],
    "grpc": [
        {"url": "https://grpc.io/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "gRPC 官方文档"},
    ],
    "graphql": [
        {"url": "https://graphql.org/learn/", "language": "en", "type": "doc", "level": "beginner", "title": "GraphQL 官方教程"},
        {"url": "https://graphql.cn/learn/", "language": "zh", "type": "doc", "level": "beginner", "title": "GraphQL 中文教程（社区）"},
    ],
    "rest": [
        {"url": "https://restfulapi.net/", "language": "en", "type": "doc", "level": "intermediate", "title": "REST API Tutorial"},
    ],
    "api-design": [
        {"url": "https://learn.openapis.org/", "language": "en", "type": "doc", "level": "intermediate", "title": "OpenAPI Learning（API 设计规范）"},
    ],
    # ----- 数据库 -----
    "mysql": [
        {"url": "https://dev.mysql.com/doc/", "language": "en", "type": "doc", "level": "beginner", "title": "MySQL 官方文档"},
    ],
    "postgresql": [
        {"url": "https://www.postgresql.org/docs/", "language": "en", "type": "doc", "level": "beginner", "title": "PostgreSQL 官方文档"},
    ],
    "mongodb": [
        {"url": "https://www.mongodb.com/docs/", "language": "en", "type": "doc", "level": "beginner", "title": "MongoDB 官方文档"},
        {"url": "https://www.mongodb.com/zh-cn/docs/", "language": "zh", "type": "doc", "level": "beginner", "title": "MongoDB 官方文档（中文）"},
    ],
    "redis": [
        {"url": "https://redis.io/docs/latest/", "language": "en", "type": "doc", "level": "beginner", "title": "Redis 官方文档"},
    ],
    "oracle-db": [
        {"url": "https://docs.oracle.com/en/database/oracle/oracle-database/", "language": "en", "type": "doc", "level": "intermediate", "title": "Oracle Database 官方文档"},
    ],
    "sqlserver": [
        {"url": "https://learn.microsoft.com/en-us/sql/sql-server/", "language": "en", "type": "doc", "level": "beginner", "title": "SQL Server 官方文档"},
        {"url": "https://learn.microsoft.com/zh-cn/sql/sql-server/", "language": "zh", "type": "doc", "level": "beginner", "title": "SQL Server 官方文档（中文）"},
    ],
    "sqlite": [
        {"url": "https://sqlite.org/docs.html", "language": "en", "type": "doc", "level": "beginner", "title": "SQLite 官方文档"},
    ],
    "cassandra": [
        {"url": "https://cassandra.apache.org/doc/latest/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Cassandra 官方文档"},
    ],
    "elasticsearch": [
        {"url": "https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html", "language": "en", "type": "doc", "level": "intermediate", "title": "Elasticsearch 官方文档"},
    ],
    "dynamodb": [
        {"url": "https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/", "language": "en", "type": "doc", "level": "intermediate", "title": "Amazon DynamoDB 官方文档"},
    ],
    "neo4j": [
        {"url": "https://neo4j.com/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Neo4j 官方文档"},
    ],
    "clickhouse": [
        {"url": "https://clickhouse.com/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "ClickHouse 官方文档"},
        {"url": "https://clickhouse.com/docs/zh", "language": "zh", "type": "doc", "level": "intermediate", "title": "ClickHouse 官方文档（中文）"},
    ],
    "mariadb": [
        {"url": "https://mariadb.com/kb/en/documentation/", "language": "en", "type": "doc", "level": "beginner", "title": "MariaDB 官方知识库"},
    ],
    "couchbase": [
        {"url": "https://docs.couchbase.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "Couchbase 官方文档"},
    ],
    "influxdb": [
        {"url": "https://docs.influxdata.com/influxdb/latest/", "language": "en", "type": "doc", "level": "intermediate", "title": "InfluxDB 官方文档"},
    ],
    "db2": [
        {"url": "https://www.ibm.com/docs/en/db2", "language": "en", "type": "doc", "level": "intermediate", "title": "IBM Db2 官方文档"},
    ],
    # ----- 云 -----
    "aws": [
        {"url": "https://docs.aws.amazon.com/", "language": "en", "type": "doc", "level": "beginner", "title": "AWS 官方文档"},
        {"url": "https://aws.amazon.com/cn/getting-started/", "language": "zh", "type": "doc", "level": "beginner", "title": "AWS 入门资源（官方中文）"},
    ],
    "azure": [
        {"url": "https://learn.microsoft.com/en-us/azure/", "language": "en", "type": "doc", "level": "beginner", "title": "Microsoft Azure 官方文档"},
        {"url": "https://learn.microsoft.com/zh-cn/azure/", "language": "zh", "type": "doc", "level": "beginner", "title": "Microsoft Azure 官方文档（中文）"},
    ],
    "gcp": [
        {"url": "https://cloud.google.com/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Google Cloud 官方文档"},
        {"url": "https://cloud.google.com/docs?hl=zh-cn", "language": "zh", "type": "doc", "level": "beginner", "title": "Google Cloud 官方文档（中文）"},
    ],
    "alicloud": [
        {"url": "https://help.aliyun.com/", "language": "zh", "type": "doc", "level": "beginner", "title": "阿里云官方文档"},
        {"url": "https://www.alibabacloud.com/help", "language": "en", "type": "doc", "level": "beginner", "title": "Alibaba Cloud 官方文档（英文）"},
    ],
    "tencent-cloud": [
        {"url": "https://cloud.tencent.com/document/product", "language": "zh", "type": "doc", "level": "beginner", "title": "腾讯云官方文档"},
    ],
    "cloudflare": [
        {"url": "https://developers.cloudflare.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "Cloudflare 开发者文档"},
    ],
    "heroku": [
        {"url": "https://devcenter.heroku.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Heroku Dev Center"},
    ],
    "digitalocean": [
        {"url": "https://docs.digitalocean.com/", "language": "en", "type": "doc", "level": "beginner", "title": "DigitalOcean 文档"},
    ],
    "s3": [
        {"url": "https://docs.aws.amazon.com/s3/", "language": "en", "type": "doc", "level": "intermediate", "title": "Amazon S3 官方文档"},
    ],
    "ec2": [
        {"url": "https://docs.aws.amazon.com/ec2/", "language": "en", "type": "doc", "level": "intermediate", "title": "Amazon EC2 官方文档"},
    ],
    "lambda": [
        {"url": "https://docs.aws.amazon.com/lambda/", "language": "en", "type": "doc", "level": "intermediate", "title": "AWS Lambda 官方文档"},
    ],
    "redshift": [
        {"url": "https://docs.aws.amazon.com/redshift/", "language": "en", "type": "doc", "level": "intermediate", "title": "Amazon Redshift 官方文档"},
    ],
    "aurora": [
        {"url": "https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/", "language": "en", "type": "doc", "level": "intermediate", "title": "Amazon Aurora 官方文档"},
    ],
    "cloudformation": [
        {"url": "https://docs.aws.amazon.com/cloudformation/", "language": "en", "type": "doc", "level": "intermediate", "title": "AWS CloudFormation 官方文档"},
    ],
    "cloud-computing": [
        {"url": "https://aws.amazon.com/what-is-cloud-computing/", "language": "en", "type": "doc", "level": "beginner", "title": "AWS：什么是云计算"},
    ],
    "edge-computing": [
        {"url": "https://www.ibm.com/cn-zh/topics/edge-computing", "language": "zh", "type": "doc", "level": "beginner", "title": "IBM：什么是边缘计算（中文）"},
    ],
    "serverless": [
        {"url": "https://www.serverless.com/framework/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "Serverless Framework 官方文档"},
    ],
    # ----- 大数据 -----
    "spark": [
        {"url": "https://spark.apache.org/docs/latest/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Spark 官方文档"},
    ],
    "hadoop": [
        {"url": "https://hadoop.apache.org/docs/stable/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Hadoop 官方文档"},
    ],
    "kafka": [
        {"url": "https://kafka.apache.org/documentation/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Kafka 官方文档"},
    ],
    "flink": [
        {"url": "https://nightlies.apache.org/flink/flink-docs-stable/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Flink 官方文档"},
        {"url": "https://nightlies.apache.org/flink/flink-docs-stable/zh/", "language": "zh", "type": "doc", "level": "intermediate", "title": "Apache Flink 官方文档（中文）"},
    ],
    "airflow": [
        {"url": "https://airflow.apache.org/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Airflow 官方文档"},
    ],
    "dbt": [
        {"url": "https://docs.getdbt.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "dbt 官方文档"},
    ],
    "hive": [
        {"url": "https://cwiki.apache.org/confluence/display/Hive/LanguageManual", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Hive 官方文档"},
    ],
    "snowflake": [
        {"url": "https://docs.snowflake.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "Snowflake 官方文档"},
    ],
    "databricks": [
        {"url": "https://docs.databricks.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "Databricks 官方文档"},
    ],
    "bigquery": [
        {"url": "https://cloud.google.com/bigquery/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "Google BigQuery 官方文档"},
    ],
    "rabbitmq": [
        {"url": "https://www.rabbitmq.com/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "RabbitMQ 官方文档"},
    ],
    "dagster": [
        {"url": "https://docs.dagster.io/", "language": "en", "type": "doc", "level": "intermediate", "title": "Dagster 官方文档"},
    ],
    "data-warehouse": [
        {"url": "https://www.ibm.com/topics/data-warehouse", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：什么是数据仓库"},
    ],
    "data-lake": [
        {"url": "https://www.ibm.com/topics/data-lake", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：什么是数据湖"},
    ],
    "data-governance": [
        {"url": "https://atlan.com/what-is-data-governance/", "language": "en", "type": "doc", "level": "beginner", "title": "Atlan：什么是数据治理"},
    ],
    "data-modeling": [
        {"url": "https://learn.microsoft.com/en-us/azure/architecture/data-guide/", "language": "en", "type": "doc", "level": "intermediate", "title": "Microsoft Azure 数据架构指南"},
    ],
    "dimensional-modeling": [
        {"url": "https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/", "language": "en", "type": "doc", "level": "intermediate", "title": "Kimball Group：维度建模技术"},
    ],
    "data-quality": [
        {"url": "https://docs.greatexpectations.io/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Great Expectations 数据质量文档"},
    ],
    "data-pipeline": [
        {"url": "https://aws.amazon.com/what-is/data-pipeline/", "language": "en", "type": "doc", "level": "beginner", "title": "AWS：什么是数据管道"},
    ],
    "etl": [
        {"url": "https://www.ibm.com/topics/etl", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：什么是 ETL"},
    ],
    "nosql": [
        {"url": "https://www.ibm.com/topics/nosql-databases", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：NoSQL 数据库介绍"},
    ],
    # ----- 数据分析 -----
    "pandas": [
        {"url": "https://pandas.pydata.org/docs/", "language": "en", "type": "doc", "level": "beginner", "title": "pandas 官方文档"},
    ],
    "numpy": [
        {"url": "https://numpy.org/doc/stable/", "language": "en", "type": "doc", "level": "beginner", "title": "NumPy 官方文档"},
    ],
    "tableau": [
        {"url": "https://help.tableau.com/current/pro/desktop/en-us/gettingstarted_overview.htm", "language": "en", "type": "doc", "level": "beginner", "title": "Tableau 官方帮助"},
    ],
    "powerbi": [
        {"url": "https://learn.microsoft.com/en-us/power-bi/", "language": "en", "type": "doc", "level": "beginner", "title": "Power BI 官方文档"},
        {"url": "https://learn.microsoft.com/zh-cn/power-bi/", "language": "zh", "type": "doc", "level": "beginner", "title": "Power BI 官方文档（中文）"},
    ],
    "excel": [
        {"url": "https://support.microsoft.com/en-us/excel", "language": "en", "type": "doc", "level": "beginner", "title": "Microsoft Excel 帮助中心"},
        {"url": "https://support.microsoft.com/zh-cn/excel", "language": "zh", "type": "doc", "level": "beginner", "title": "Microsoft Excel 帮助中心（中文）"},
    ],
    "looker": [
        {"url": "https://cloud.google.com/looker/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "Looker 官方文档"},
    ],
    "data-analysis": [
        {"url": "https://www.khanacademy.org/math/statistics-probability", "language": "en", "type": "course", "level": "beginner", "title": "Khan Academy 统计与概率（免费）"},
    ],
    "statistics": [
        {"url": "https://www.openintro.org/book/os/", "language": "en", "type": "book", "level": "beginner", "title": "OpenIntro Statistics（免费开源教材）"},
    ],
    "data-visualization": [
        {"url": "https://www.data-to-viz.com/", "language": "en", "type": "doc", "level": "beginner", "title": "From Data to Viz（图表选择指南）"},
    ],
    "data-mining": [
        {"url": "https://www.ibm.com/topics/data-mining", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：什么是数据挖掘"},
    ],
    "business-intelligence": [
        {"url": "https://www.ibm.com/topics/business-intelligence", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：什么是商业智能"},
    ],
    "dashboard": [
        {"url": "https://www.ibm.com/topics/dashboard", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：什么是数据仪表板"},
    ],
    "data-cleaning": [
        {"url": "https://www.ibm.com/topics/data-cleansing", "language": "en", "type": "doc", "level": "beginner", "title": "IBM：什么是数据清洗"},
    ],
    "hypothesis-testing": [
        {"url": "https://www.statisticsbyjim.com/hypothesis-testing/", "language": "en", "type": "doc", "level": "intermediate", "title": "Statistics By Jim：假设检验"},
    ],
    "time-series": [
        {"url": "https://www.ibm.com/cn-zh/topics/time-series", "language": "zh", "type": "book", "level": "intermediate", "title": "IBM：时间序列分析（中文）"},
    ],
    "ab-testing": [
        {"url": "https://www.evanmiller.org/ab-testing/", "language": "en", "type": "doc", "level": "intermediate", "title": "Evan Miller：A/B 测试样本量与显著性工具"},
    ],
    # ----- AI/ML -----
    "machine-learning": [
        {"url": "https://developers.google.com/machine-learning/crash-course", "language": "en", "type": "course", "level": "beginner", "title": "Google Machine Learning Crash Course（免费）"},
        {"url": "https://www.coursera.org/learn/machine-learning", "language": "en", "type": "course", "level": "beginner", "title": "吴恩达 Machine Learning（Coursera 可旁听）"},
        {"url": "https://zh.d2l.ai/", "language": "zh", "type": "book", "level": "beginner", "title": "《动手学深度学习》（李沐，中文+视频）"},
    ],
    "deep-learning": [
        {"url": "https://www.deeplearningbook.org/", "language": "en", "type": "book", "level": "intermediate", "title": "Deep Learning（Goodfellow 等，免费在线）"},
        {"url": "https://course.fast.ai/", "language": "en", "type": "course", "level": "intermediate", "title": "fast.ai Practical Deep Learning（免费）"},
    ],
    "pytorch": [
        {"url": "https://pytorch.org/docs/stable/index.html", "language": "en", "type": "doc", "level": "intermediate", "title": "PyTorch 官方文档"},
        {"url": "https://pytorch.apachecn.org/", "language": "zh", "type": "doc", "level": "intermediate", "title": "PyTorch 中文文档（ApacheCN）"},
    ],
    "tensorflow": [
        {"url": "https://www.tensorflow.org/guide", "language": "en", "type": "doc", "level": "intermediate", "title": "TensorFlow 官方指南"},
        {"url": "https://www.tensorflow.org/guide?hl=zh-cn", "language": "zh", "type": "doc", "level": "intermediate", "title": "TensorFlow 官方指南（中文）"},
    ],
    "keras": [
        {"url": "https://keras.io/guides/", "language": "en", "type": "doc", "level": "intermediate", "title": "Keras 官方指南"},
    ],
    "scikit-learn": [
        {"url": "https://scikit-learn.org/stable/user_guide.html", "language": "en", "type": "doc", "level": "intermediate", "title": "scikit-learn 用户指南"},
    ],
    "nlp": [
        {"url": "https://web.stanford.edu/~jurafsky/slp3/", "language": "en", "type": "book", "level": "intermediate", "title": "Speech and Language Processing（Jurafsky & Martin，免费草稿）"},
    ],
    "computer-vision": [
        {"url": "https://cs231n.github.io/", "language": "en", "type": "course", "level": "intermediate", "title": "Stanford CS231n 课程笔记（CNN 与视觉识别）"},
    ],
    "reinforcement-learning": [
        {"url": "http://incompleteideas.net/book/the-book-2nd.html", "language": "en", "type": "book", "level": "intermediate", "title": "Reinforcement Learning: An Introduction（Sutton & Barto，免费）"},
    ],
    "xgboost": [
        {"url": "https://xgboost.readthedocs.io/", "language": "en", "type": "doc", "level": "intermediate", "title": "XGBoost 官方文档"},
    ],
    "data-science": [
        {"url": "https://www.kaggle.com/learn/overview", "language": "en", "type": "course", "level": "beginner", "title": "Kaggle Learn（免费微课程）"},
        {"url": "https://jakevdp.github.io/PythonDataScienceHandbook/", "language": "en", "type": "book", "level": "intermediate", "title": "Python Data Science Handbook（免费在线）"},
    ],
    "jupyter": [
        {"url": "https://docs.jupyter.org/", "language": "en", "type": "doc", "level": "beginner", "title": "Jupyter 官方文档"},
    ],
    "cuda": [
        {"url": "https://docs.nvidia.com/cuda/", "language": "en", "type": "doc", "level": "advanced", "title": "NVIDIA CUDA 官方文档"},
    ],
    "supervised-learning": [
        {"url": "https://scikit-learn.org/stable/supervised_learning.html", "language": "en", "type": "doc", "level": "beginner", "title": "scikit-learn：监督学习指南"},
    ],
    "unsupervised-learning": [
        {"url": "https://scikit-learn.org/stable/unsupervised_learning.html", "language": "en", "type": "doc", "level": "intermediate", "title": "scikit-learn：无监督学习指南"},
    ],
    "model-evaluation": [
        {"url": "https://scikit-learn.org/stable/modules/model_evaluation.html", "language": "en", "type": "doc", "level": "intermediate", "title": "scikit-learn：模型评估指南"},
    ],
    "bert": [
        {"url": "https://huggingface.co/docs/transformers/model_doc/bert", "language": "en", "type": "doc", "level": "advanced", "title": "Hugging Face：BERT 模型文档"},
    ],
    "gnn": [
        {"url": "https://pytorch-geometric.readthedocs.io/", "language": "en", "type": "doc", "level": "advanced", "title": "PyTorch Geometric 官方文档（图神经网络）"},
    ],
    "cnn": [
        {"url": "https://cs231n.github.io/convolutional-networks/", "language": "en", "type": "tutorial", "level": "intermediate", "title": "CS231n：卷积神经网络笔记"},
    ],
    "rnn": [
        {"url": "https://colah.github.io/posts/2015-08-Understanding-LSTMs/", "language": "en", "type": "tutorial", "level": "intermediate", "title": "Colah's Blog：理解 LSTM 网络"},
    ],
    "ner": [
        {"url": "https://huggingface.co/tasks/token-classification", "language": "en", "type": "doc", "level": "intermediate", "title": "Hugging Face：Token 分类（NER）任务"},
    ],
    "text-classification": [
        {"url": "https://huggingface.co/tasks/text-classification", "language": "en", "type": "doc", "level": "intermediate", "title": "Hugging Face：文本分类任务"},
    ],
    "sentiment-analysis": [
        {"url": "https://huggingface.co/tasks/text-classification", "language": "en", "type": "doc", "level": "beginner", "title": "Hugging Face：文本分类（情感分析）任务"},
    ],
    "information-extraction": [
        {"url": "https://huggingface.co/tasks", "language": "en", "type": "doc", "level": "intermediate", "title": "Hugging Face：NLP 任务总览"},
    ],
    "quantization": [
        {"url": "https://huggingface.co/docs/optimum/index", "language": "en", "type": "doc", "level": "advanced", "title": "Hugging Face Optimum（量化优化）文档"},
    ],
    "feature-engineering": [
        {"url": "https://scikit-learn.org/stable/modules/preprocessing.html", "language": "en", "type": "doc", "level": "intermediate", "title": "scikit-learn：预处理与特征工程"},
    ],
    # ----- LLM / 生成式 AI -----
    "llm": [
        {"url": "https://stanford-cs336.github.io/spring2024/", "language": "en", "type": "course", "level": "advanced", "title": "Stanford CS336：Language Modeling from Scratch"},
    ],
    "rag": [
        {"url": "https://docs.llamaindex.ai/", "language": "en", "type": "doc", "level": "intermediate", "title": "LlamaIndex 文档（RAG 开发框架）"},
    ],
    "langchain": [
        {"url": "https://python.langchain.com/docs/introduction/", "language": "en", "type": "doc", "level": "intermediate", "title": "LangChain 官方文档"},
    ],
    "llamaindex": [
        {"url": "https://docs.llamaindex.ai/", "language": "en", "type": "doc", "level": "intermediate", "title": "LlamaIndex 官方文档"},
    ],
    "langgraph": [
        {"url": "https://langchain-ai.github.io/langgraph/", "language": "en", "type": "doc", "level": "intermediate", "title": "LangGraph 官方文档"},
    ],
    "vector-database": [
        {"url": "https://www.pinecone.io/learn/vector-database/", "language": "en", "type": "doc", "level": "beginner", "title": "Pinecone：什么是向量数据库"},
    ],
    "pinecone": [
        {"url": "https://docs.pinecone.io/", "language": "en", "type": "doc", "level": "intermediate", "title": "Pinecone 官方文档"},
    ],
    "milvus": [
        {"url": "https://milvus.io/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "Milvus 官方文档"},
    ],
    "weaviate": [
        {"url": "https://docs.weaviate.io/", "language": "en", "type": "doc", "level": "intermediate", "title": "Weaviate 官方文档"},
    ],
    "chroma": [
        {"url": "https://docs.trychroma.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "Chroma 官方文档"},
    ],
    "faiss": [
        {"url": "https://faiss.ai/", "language": "en", "type": "doc", "level": "advanced", "title": "FAISS 官方文档（向量相似度检索）"},
    ],
    "embedding": [
        {"url": "https://platform.openai.com/docs/guides/embeddings", "language": "en", "type": "doc", "level": "intermediate", "title": "OpenAI Embeddings 指南"},
    ],
    "prompt-engineering": [
        {"url": "https://platform.openai.com/docs/guides/prompt-engineering", "language": "en", "type": "doc", "level": "beginner", "title": "OpenAI Prompt Engineering 指南"},
        {"url": "https://www.deeplearning.ai/short-courses/chatgpt-prompt-engineering-for-developers/", "language": "en", "type": "course", "level": "beginner", "title": "DeepLearning.AI：面向开发者的提示工程（免费短课）"},
    ],
    "fine-tuning": [
        {"url": "https://huggingface.co/docs/peft/index", "language": "en", "type": "doc", "level": "advanced", "title": "Hugging Face PEFT（LoRA/QLoRA 微调）文档"},
    ],
    "agent": [
        {"url": "https://huggingface.co/learn/agents-course", "language": "en", "type": "course", "level": "intermediate", "title": "Hugging Face Agents Course（免费）"},
    ],
    "transformer": [
        {"url": "https://jalammar.github.io/illustrated-transformer/", "language": "en", "type": "tutorial", "level": "intermediate", "title": "The Illustrated Transformer（图解 Transformer）"},
        {"url": "https://arxiv.org/abs/1706.03762", "language": "en", "type": "doc", "level": "advanced", "title": "论文：Attention Is All You Need"},
    ],
    "gpt": [
        {"url": "https://platform.openai.com/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "OpenAI 官方文档"},
    ],
    "huggingface": [
        {"url": "https://huggingface.co/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Hugging Face 官方文档"},
    ],
    "openai-api": [
        {"url": "https://platform.openai.com/docs/api-reference", "language": "en", "type": "doc", "level": "intermediate", "title": "OpenAI API Reference"},
    ],
    "tool-calling": [
        {"url": "https://platform.openai.com/docs/guides/function-calling", "language": "en", "type": "doc", "level": "intermediate", "title": "OpenAI Function Calling 指南"},
    ],
    "mlops": [
        {"url": "https://ml-ops.org/", "language": "en", "type": "doc", "level": "intermediate", "title": "MLOps 社区知识库"},
        {"url": "https://madewithml.com/", "language": "en", "type": "course", "level": "intermediate", "title": "Made With ML（MLOps 免费课程）"},
    ],
    "mcp": [
        {"url": "https://modelcontextprotocol.io/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "Model Context Protocol 官方文档"},
    ],
    "multimodal": [
        {"url": "https://huggingface.co/docs/transformers/en/model_doc/clip", "language": "en", "type": "doc", "level": "advanced", "title": "Hugging Face：CLIP 多模态模型文档"},
    ],
    "diffusion": [
        {"url": "https://huggingface.co/docs/diffusers/index", "language": "en", "type": "doc", "level": "advanced", "title": "Hugging Face Diffusers 官方文档"},
    ],
    "knowledge-graph": [
        {"url": "https://neo4j.com/docs/getting-started/", "language": "en", "type": "tutorial", "level": "intermediate", "title": "Neo4j 官方入门文档（含图数据/知识图谱）"},
    ],
    "aigc": [
        {"url": "https://huggingface.co/learn/diffusion-course", "language": "en", "type": "course", "level": "intermediate", "title": "Hugging Face Diffusion Models Course（免费）"},
    ],
    "multi-agent": [
        {"url": "https://langchain-ai.github.io/langgraph/concepts/multi_agent/", "language": "en", "type": "doc", "level": "advanced", "title": "LangGraph：多智能体架构概念"},
    ],
    "coze": [
        {"url": "https://www.coze.cn/docs/developer_guides/coze_overview", "language": "zh", "type": "doc", "level": "beginner", "title": "扣子（Coze）官方开发文档"},
    ],
    "qwen": [
        {"url": "https://help.aliyun.com/zh/dashscope/", "language": "zh", "type": "doc", "level": "intermediate", "title": "阿里云百炼（DashScope）模型服务文档"},
    ],
    "model-deployment": [
        {"url": "https://huggingface.co/docs/hub/spaces", "language": "en", "type": "doc", "level": "intermediate", "title": "Hugging Face Spaces（模型部署）文档"},
    ],
    "recommendation-system": [
        {"url": "https://recbole.io/docs/", "language": "en", "type": "doc", "level": "advanced", "title": "RecBole 推荐系统框架文档"},
    ],
    # ----- DevOps -----
    "docker": [
        {"url": "https://docs.docker.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Docker 官方文档"},
    ],
    "kubernetes": [
        {"url": "https://kubernetes.io/docs/home/", "language": "en", "type": "doc", "level": "intermediate", "title": "Kubernetes 官方文档"},
        {"url": "https://kubernetes.io/zh-cn/docs/home/", "language": "zh", "type": "doc", "level": "intermediate", "title": "Kubernetes 官方文档（中文）"},
    ],
    "terraform": [
        {"url": "https://developer.hashicorp.com/terraform/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "Terraform 官方文档"},
    ],
    "ansible": [
        {"url": "https://docs.ansible.com/ansible/latest/", "language": "en", "type": "doc", "level": "intermediate", "title": "Ansible 官方文档"},
    ],
    "jenkins": [
        {"url": "https://www.jenkins.io/doc/", "language": "en", "type": "doc", "level": "intermediate", "title": "Jenkins 官方文档"},
    ],
    "gitlab-ci": [
        {"url": "https://docs.gitlab.com/ee/ci/", "language": "en", "type": "doc", "level": "intermediate", "title": "GitLab CI/CD 官方文档"},
    ],
    "github-actions": [
        {"url": "https://docs.github.com/en/actions", "language": "en", "type": "doc", "level": "beginner", "title": "GitHub Actions 官方文档"},
    ],
    "cicd": [
        {"url": "https://docs.gitlab.com/ee/ci/", "language": "en", "type": "doc", "level": "beginner", "title": "GitLab：什么是 CI/CD"},
    ],
    "helm": [
        {"url": "https://helm.sh/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Helm 官方文档"},
    ],
    "prometheus": [
        {"url": "https://prometheus.io/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Prometheus 官方文档"},
    ],
    "grafana": [
        {"url": "https://grafana.com/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Grafana 官方文档"},
    ],
    "nginx": [
        {"url": "https://nginx.org/en/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Nginx 官方文档"},
    ],
    "linux": [
        {"url": "https://man7.org/linux/man-pages/", "language": "en", "type": "doc", "level": "intermediate", "title": "Linux man-pages（man7.org）"},
        {"url": "https://linux.vbird.org/", "language": "zh", "type": "book", "level": "beginner", "title": "鸟哥的 Linux 私房菜（中文经典）"},
    ],
    "unix": [
        {"url": "https://man7.org/linux/man-pages/", "language": "en", "type": "doc", "level": "intermediate", "title": "Unix/Linux man-pages"},
    ],
    "git": [
        {"url": "https://git-scm.com/doc", "language": "en", "type": "doc", "level": "beginner", "title": "Git 官方文档"},
        {"url": "https://git-scm.com/book/zh/v2", "language": "zh", "type": "book", "level": "beginner", "title": "Pro Git（官方中文版）"},
    ],
    "devops": [
        {"url": "https://aws.amazon.com/devops/what-is-devops/", "language": "en", "type": "doc", "level": "beginner", "title": "AWS：什么是 DevOps"},
    ],
    "microservices": [
        {"url": "https://microservices.io/", "language": "en", "type": "doc", "level": "intermediate", "title": "microservices.io（Chris Richardson）"},
    ],
    "argocd": [
        {"url": "https://argo-cd.readthedocs.io/", "language": "en", "type": "doc", "level": "intermediate", "title": "Argo CD 官方文档"},
    ],
    "vagrant": [
        {"url": "https://developer.hashicorp.com/vagrant/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Vagrant 官方文档"},
    ],
    "istio": [
        {"url": "https://istio.io/latest/docs/", "language": "en", "type": "doc", "level": "advanced", "title": "Istio 官方文档（Service Mesh）"},
    ],
    "caching": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching", "language": "en", "type": "doc", "level": "intermediate", "title": "MDN：HTTP 缓存"},
    ],
    "high-availability": [
        {"url": "https://www.ibm.com/cn-zh/topics/high-availability", "language": "zh", "type": "doc", "level": "intermediate", "title": "IBM：什么是高可用（中文）"},
    ],
    "load-balancing": [
        {"url": "https://www.nginx.com/resources/glossary/load-balancing/", "language": "en", "type": "doc", "level": "intermediate", "title": "NGINX：负载均衡术语与算法"},
    ],
    "message-queue": [
        {"url": "https://www.rabbitmq.com/tutorials", "language": "en", "type": "tutorial", "level": "intermediate", "title": "RabbitMQ 官方教程（消息队列）"},
    ],
    "performance-tuning": [
        {"url": "https://brendangregg.com/", "language": "en", "type": "doc", "level": "advanced", "title": "Brendan Gregg 性能分析（业界权威）"},
    ],
    "sre": [
        {"url": "https://sre.google/sre-book/table-of-contents/", "language": "en", "type": "book", "level": "advanced", "title": "Google SRE 手册（免费在线）"},
    ],
    # ----- 测试 -----
    "selenium": [
        {"url": "https://www.selenium.dev/documentation/", "language": "en", "type": "doc", "level": "intermediate", "title": "Selenium 官方文档"},
    ],
    "cypress": [
        {"url": "https://docs.cypress.io/", "language": "en", "type": "doc", "level": "intermediate", "title": "Cypress 官方文档"},
    ],
    "playwright": [
        {"url": "https://playwright.dev/docs/intro", "language": "en", "type": "doc", "level": "intermediate", "title": "Playwright 官方文档"},
    ],
    "jest": [
        {"url": "https://jestjs.io/docs/getting-started", "language": "en", "type": "doc", "level": "intermediate", "title": "Jest 官方文档"},
    ],
    "pytest": [
        {"url": "https://docs.pytest.org/", "language": "en", "type": "doc", "level": "intermediate", "title": "pytest 官方文档"},
    ],
    "junit": [
        {"url": "https://junit.org/junit5/docs/current/user-guide/", "language": "en", "type": "doc", "level": "intermediate", "title": "JUnit 5 用户指南"},
    ],
    "appium": [
        {"url": "https://appium.io/docs/en/latest/", "language": "en", "type": "doc", "level": "intermediate", "title": "Appium 官方文档"},
    ],
    "jmeter": [
        {"url": "https://jmeter.apache.org/usermanual/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache JMeter 用户手册"},
    ],
    "postman": [
        {"url": "https://learning.postman.com/docs/introduction/overview/", "language": "en", "type": "doc", "level": "beginner", "title": "Postman 官方学习文档"},
    ],
    "unit-testing": [
        {"url": "https://martinfowler.com/articles/practical-test-pyramid.html", "language": "en", "type": "doc", "level": "intermediate", "title": "Martin Fowler：测试金字塔实践"},
    ],
    "integration-testing": [
        {"url": "https://martinfowler.com/articles/practical-test-pyramid.html", "language": "en", "type": "doc", "level": "intermediate", "title": "Martin Fowler：测试金字塔实践"},
    ],
    "load-testing": [
        {"url": "https://k6.io/docs/", "language": "en", "type": "doc", "level": "intermediate", "title": "Grafana k6 负载测试文档"},
    ],
    "qa-automation": [
        {"url": "https://www.selenium.dev/documentation/", "language": "en", "type": "doc", "level": "intermediate", "title": "Selenium 官方文档（自动化测试）"},
    ],
    # ----- 移动 -----
    "android": [
        {"url": "https://developer.android.com/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Android 开发者官方文档"},
        {"url": "https://developer.android.google.cn/docs", "language": "zh", "type": "doc", "level": "beginner", "title": "Android 开发者官方文档（中文镜像）"},
    ],
    "ios": [
        {"url": "https://developer.apple.com/documentation/", "language": "en", "type": "doc", "level": "intermediate", "title": "Apple 开发者官方文档"},
    ],
    "flutter": [
        {"url": "https://docs.flutter.dev/", "language": "en", "type": "doc", "level": "beginner", "title": "Flutter 官方文档"},
        {"url": "https://flutter.cn/docs", "language": "zh", "type": "doc", "level": "beginner", "title": "Flutter 官方文档（中文社区）"},
    ],
    "react-native": [
        {"url": "https://reactnative.dev/docs/getting-started", "language": "en", "type": "doc", "level": "intermediate", "title": "React Native 官方文档"},
    ],
    "xamarin": [
        {"url": "https://learn.microsoft.com/en-us/xamarin/", "language": "en", "type": "doc", "level": "intermediate", "title": "Microsoft Xamarin 文档"},
    ],
    "jetpack-compose": [
        {"url": "https://developer.android.com/jetpack/compose/documentation", "language": "en", "type": "doc", "level": "intermediate", "title": "Jetpack Compose 官方文档"},
    ],
    # ----- 安全 -----
    "cybersecurity": [
        {"url": "https://owasp.org/", "language": "en", "type": "doc", "level": "beginner", "title": "OWASP 官网（Web 安全权威）"},
    ],
    "penetration-testing": [
        {"url": "https://owasp.org/www-project-web-security-testing-guide/", "language": "en", "type": "doc", "level": "advanced", "title": "OWASP Web 安全测试指南（WSTG）"},
    ],
    "oauth": [
        {"url": "https://oauth.net/2/", "language": "en", "type": "doc", "level": "intermediate", "title": "OAuth 2.0 官方资料（oauth.net）"},
    ],
    "jwt": [
        {"url": "https://jwt.io/introduction", "language": "en", "type": "doc", "level": "intermediate", "title": "JWT 官方介绍（jwt.io）"},
    ],
    "ssl-tls": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security", "language": "en", "type": "doc", "level": "intermediate", "title": "MDN：传输层安全（TLS）"},
    ],
    "owasp": [
        {"url": "https://owasp.org/www-project-top-ten/", "language": "en", "type": "doc", "level": "intermediate", "title": "OWASP Top 10（官方）"},
    ],
    "zero-trust": [
        {"url": "https://www.ibm.com/cn-zh/topics/zero-trust", "language": "zh", "type": "doc", "level": "intermediate", "title": "IBM：什么是零信任（中文）"},
    ],
    "cryptography": [
        {"url": "https://cryptohack.org/", "language": "en", "type": "interactive", "level": "advanced", "title": "CryptoHack（交互式密码学练习）"},
    ],
    "encryption": [
        {"url": "https://cryptopals.com/", "language": "en", "type": "interactive", "level": "advanced", "title": "Cryptopals（密码学攻防练习）"},
    ],
    "iam": [
        {"url": "https://docs.aws.amazon.com/IAM/latest/UserGuide/", "language": "en", "type": "doc", "level": "intermediate", "title": "AWS IAM 官方用户指南"},
    ],
    "siem": [
        {"url": "https://docs.splunk.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "Splunk 官方文档（SIEM）"},
    ],
    "vulnerability-assessment": [
        {"url": "https://www.cve.org/", "language": "en", "type": "doc", "level": "intermediate", "title": "CVE 官方漏洞库（MITRE）"},
    ],
    "data-privacy": [
        {"url": "https://gdpr.eu/", "language": "en", "type": "doc", "level": "intermediate", "title": "GDPR.eu 数据隐私指南"},
    ],
    # ----- 工程方法/其他 -----
    "agile": [
        {"url": "https://agilemanifesto.org/", "language": "en", "type": "doc", "level": "beginner", "title": "敏捷宣言（官方）"},
        {"url": "https://agilemanifesto.org/iso/zhchs/manifesto.html", "language": "zh", "type": "doc", "level": "beginner", "title": "敏捷宣言（官方中文版）"},
    ],
    "scrum": [
        {"url": "https://scrumguides.org/scrum-guide.html", "language": "en", "type": "doc", "level": "beginner", "title": "Scrum Guide（官方）"},
    ],
    "kanban": [
        {"url": "https://www.atlassian.com/agile/kanban", "language": "en", "type": "doc", "level": "beginner", "title": "Atlassian：看板方法指南"},
    ],
    "jira": [
        {"url": "https://support.atlassian.com/jira-software-cloud/", "language": "en", "type": "doc", "level": "beginner", "title": "Atlassian Jira 官方支持文档"},
    ],
    "confluence": [
        {"url": "https://support.atlassian.com/confluence-cloud/", "language": "en", "type": "doc", "level": "beginner", "title": "Atlassian Confluence 官方支持文档"},
    ],
    "json": [
        {"url": "https://www.json.org/json-en.html", "language": "en", "type": "doc", "level": "beginner", "title": "JSON 官方介绍（json.org）"},
    ],
    "xml": [
        {"url": "https://developer.mozilla.org/en-US/docs/Web/XML", "language": "en", "type": "doc", "level": "beginner", "title": "MDN XML 文档"},
    ],
    "oop": [
        {"url": "https://www.pythontutor.com/", "language": "en", "type": "interactive", "level": "beginner", "title": "Python Tutor（代码可视化执行，学 OOP/调试）"},
    ],
    "system-design": [
        {"url": "https://github.com/donnemartin/system-design-primer", "language": "en", "type": "doc", "level": "intermediate", "title": "System Design Primer（GitHub 26万+ stars）"},
        {"url": "https://xiaolincoding.com/", "language": "zh", "type": "tutorial", "level": "intermediate", "title": "小林 coding（图解计算机基础/网络/系统，中文）"},
    ],
    "distributed-systems": [
        {"url": "https://pdos.csail.mit.edu/6.824/", "language": "en", "type": "course", "level": "advanced", "title": "MIT 6.824 分布式系统（公开课程）"},
    ],
    "blockchain": [
        {"url": "https://www.ibm.com/topics/blockchain", "language": "en", "type": "doc", "level": "intermediate", "title": "IBM：什么是区块链（ethereum.org 本网络不可达）"},
        {"url": "https://learnblockchain.cn/", "language": "zh", "type": "doc", "level": "intermediate", "title": "登链社区（中文区块链/Web3 学习）"},
    ],
    "data-structures": [
        {"url": "https://visualgo.net/en", "language": "en", "type": "interactive", "level": "beginner", "title": "VisuAlgo（数据结构与算法可视化）"},
        {"url": "https://cs50.harvard.edu/x/", "language": "en", "type": "course", "level": "beginner", "title": "Harvard CS50（免费公开课程，含中文社区字幕）"},
        {"url": "https://leetcode.cn/", "language": "zh", "type": "interactive", "level": "intermediate", "title": "力扣 LeetCode（算法练习，中文站）"},
    ],
    "algorithms": [
        {"url": "https://visualgo.net/en", "language": "en", "type": "interactive", "level": "beginner", "title": "VisuAlgo（算法可视化）"},
        {"url": "https://neetcode.io/", "language": "en", "type": "interactive", "level": "intermediate", "title": "NeetCode（算法练习路线，免费）"},
        {"url": "https://www.bigocheatsheet.com/", "language": "en", "type": "doc", "level": "intermediate", "title": "Big-O Cheat Sheet"},
    ],
    "design-patterns": [
        {"url": "https://refactoring.guru/design-patterns", "language": "en", "type": "doc", "level": "intermediate", "title": "Refactoring.Guru 设计模式（免费章节）"},
    ],
    "regex": [
        {"url": "https://regex101.com/", "language": "en", "type": "interactive", "level": "beginner", "title": "regex101（正则交互练习）"},
    ],
    "web-scraping": [
        {"url": "https://docs.scrapy.org/", "language": "en", "type": "doc", "level": "intermediate", "title": "Scrapy 官方文档"},
    ],
    "figma": [
        {"url": "https://help.figma.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Figma 官方帮助中心"},
    ],
    "ui-ux": [
        {"url": "https://www.nngroup.com/articles/", "language": "en", "type": "doc", "level": "intermediate", "title": "Nielsen Norman Group：UX 研究文章"},
    ],
    "unity": [
        {"url": "https://docs.unity3d.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Unity 官方文档"},
    ],
    "robotics": [
        {"url": "https://docs.ros.org/", "language": "en", "type": "doc", "level": "intermediate", "title": "ROS 官方文档（机器人操作系统）"},
    ],
    "embedded": [
        {"url": "https://docs.arduino.cc/", "language": "en", "type": "doc", "level": "beginner", "title": "Arduino 官方文档（嵌入式入门）"},
    ],
    "microsoft-office": [
        {"url": "https://support.microsoft.com/training", "language": "en", "type": "tutorial", "level": "beginner", "title": "Microsoft 官方培训（Office）"},
        {"url": "https://support.microsoft.com/zh-cn/training", "language": "zh", "type": "tutorial", "level": "beginner", "title": "Microsoft 官方培训（中文）"},
    ],
    "salesforce": [
        {"url": "https://trailhead.salesforce.com/", "language": "en", "type": "interactive", "level": "beginner", "title": "Salesforce Trailhead（官方免费学习平台）"},
    ],
    "sap": [
        {"url": "https://learning.sap.com/", "language": "en", "type": "course", "level": "beginner", "title": "SAP Learning（官方免费课程）"},
    ],
    "seo": [
        {"url": "https://developers.google.com/search/docs", "language": "en", "type": "doc", "level": "intermediate", "title": "Google Search 官方文档（SEO）"},
        {"url": "https://developers.google.com/search/docs?hl=zh-cn", "language": "zh", "type": "doc", "level": "intermediate", "title": "Google Search 官方文档（中文）"},
    ],
    "sem": [
        {"url": "https://skillshop.withgoogle.com/", "language": "en", "type": "doc", "level": "beginner", "title": "Google Skillshop（Google Ads 官方免费课程）"},
    ],
    "hubspot": [
        {"url": "https://academy.hubspot.com/", "language": "en", "type": "course", "level": "beginner", "title": "HubSpot Academy（官方免费课程）"},
    ],
    "crm": [
        {"url": "https://academy.hubspot.com/", "language": "en", "type": "course", "level": "beginner", "title": "HubSpot Academy（CRM 免费课程）"},
    ],
    "documentation": [
        {"url": "https://diataxis.fr/", "language": "en", "type": "doc", "level": "intermediate", "title": "Diátaxis 技术文档框架（业界标准）"},
    ],
    "software-engineering": [
        {"url": "https://cs.ossu.dev/", "language": "en", "type": "course", "level": "beginner", "title": "OSSU 计算机科学自学路径（完全免费）"},
    ],
    "git": [
        {"url": "https://learngitbranching.js.org/", "language": "en", "type": "interactive", "level": "beginner", "title": "Learn Git Branching（交互式 Git 学习）"},
        {"url": "https://www.liaoxuefeng.com/wiki/896043488029600", "language": "zh", "type": "tutorial", "level": "beginner", "title": "廖雪峰 Git 教程"},
    ],
    "fullstack-general": [],
}

# ---------------------------------------------------------------------------
# v4.1 增补：主要补热门技能的中文权威资源（首轮 QC 显示 68 个热门技能无中文资源）
# ---------------------------------------------------------------------------
CURATED_DOCS_EXTRA = {
    "llm": [
        {"url": "https://modelscope.cn/docs", "language": "zh", "type": "doc", "level": "intermediate", "title": "魔搭社区 ModelScope 官方文档（中文大模型平台）"},
        {"url": "https://github.com/datawhalechina/llm-universe", "language": "zh", "type": "project", "level": "beginner", "title": "DataWhale《大模型应用开发》开源教程（含 RAG 实战）"},
    ],
    "rag": [
        {"url": "https://github.com/datawhalechina/llm-universe", "language": "zh", "type": "project", "level": "beginner", "title": "DataWhale《大模型应用开发》：RAG 项目实战（中文）"},
    ],
    "agent": [
        {"url": "https://modelscope.cn/docs", "language": "zh", "type": "doc", "level": "intermediate", "title": "魔搭社区 Agent 开发文档（中文）"},
    ],
    "aigc": [
        {"url": "https://modelscope.cn/docs", "language": "zh", "type": "doc", "level": "beginner", "title": "魔搭社区 AIGC 模型与创作教程（中文）"},
    ],
    "fine-tuning": [
        {"url": "https://github.com/datawhalechina/self-llm", "language": "zh", "type": "project", "level": "intermediate", "title": "DataWhale《开源大模型食用指南》：微调与部署实战（中文）"},
    ],
    "prompt-engineering": [
        {"url": "https://github.com/datawhalechina/prompt-engineering-for-developers", "language": "zh", "type": "course", "level": "beginner", "title": "DataWhale《面向开发者的提示工程》（吴恩达课程中文改良版）"},
    ],
    "transformer": [
        {"url": "https://github.com/datawhalechina/tiny-universe", "language": "zh", "type": "project", "level": "advanced", "title": "DataWhale Tiny-Universe：从零手搓大模型/Transformer（中文）"},
    ],
    "data-science": [
        {"url": "https://github.com/datawhalechina", "language": "zh", "type": "course", "level": "beginner", "title": "DataWhale 开源学习社区（数据分析/机器学习中文组队学习）"},
    ],
    "machine-learning": [
        {"url": "https://github.com/datawhalechina", "language": "zh", "type": "course", "level": "beginner", "title": "DataWhale 开源学习社区（机器学习中文教程）"},
    ],
    "openai-api": [
        {"url": "https://platform.deepseek.com/docs", "language": "zh", "type": "doc", "level": "intermediate", "title": "DeepSeek 开放平台 API 文档（中文，同类 LLM API）", "note": "同类中文 LLM API 文档"},
    ],
    "gpt": [
        {"url": "https://platform.deepseek.com/docs", "language": "zh", "type": "doc", "level": "intermediate", "title": "DeepSeek 开放平台文档（中文 LLM 平台）", "note": "同类中文 LLM API 文档"},
    ],
    "elasticsearch": [
        {"url": "https://www.elastic.co/guide/cn/elasticsearch/guide/current/index.html", "language": "zh", "type": "book", "level": "intermediate", "title": "《Elasticsearch 权威指南》中文版（Elastic 官方托管）"},
    ],
    "milvus": [
        {"url": "https://milvus.io/zh/docs", "language": "zh", "type": "doc", "level": "intermediate", "title": "Milvus 官方文档（中文）"},
    ],
    "vector-database": [
        {"url": "https://milvus.io/zh/docs", "language": "zh", "type": "doc", "level": "intermediate", "title": "Milvus 向量数据库文档（中文）"},
    ],
    "nestjs": [
        {"url": "https://docs.nestjs.cn/", "language": "zh", "type": "doc", "level": "intermediate", "title": "NestJS 中文文档（社区）"},
    ],
    "coze": [
        {"url": "https://www.coze.com/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Coze 官方文档（国际版）"},
    ],
    "dagster": [
        {"url": "https://courses.dagster.io/", "language": "en", "type": "course", "level": "beginner", "title": "Dagster University（官方免费课程）"},
        {"url": "https://github.com/dagster-io/dagster", "language": "en", "type": "project", "level": "intermediate", "title": "Dagster 官方仓库（含示例项目）"},
    ],
    "perl": [
        {"url": "https://learn.perl.org/", "language": "en", "type": "tutorial", "level": "beginner", "title": "learn.perl.org（Perl 官方入门）"},
    ],
    "hive": [
        {"url": "https://cwiki.apache.org/confluence/display/Hive/LanguageManual", "language": "en", "type": "doc", "level": "intermediate", "title": "Apache Hive Language Manual（官方 Wiki）"},
        {"url": "https://help.aliyun.com/zh/emr/", "language": "zh", "type": "doc", "level": "intermediate", "title": "阿里云 E-MapReduce 文档（含 Hive，中文）"},
    ],
    "kafka": [
        {"url": "https://kafka.apachecn.org/", "language": "zh", "type": "doc", "level": "intermediate", "title": "Kafka 中文文档（ApacheCN 社区翻译）"},
    ],
    "spark": [
        {"url": "https://spark.apachecn.org/", "language": "zh", "type": "doc", "level": "intermediate", "title": "Spark 中文文档（ApacheCN 社区翻译）"},
    ],
    "airflow": [
        {"url": "https://airflow.apachecn.org/", "language": "zh", "type": "doc", "level": "intermediate", "title": "Airflow 中文文档（ApacheCN 社区翻译）"},
    ],
    "cicd": [
        {"url": "https://help.aliyun.com/zh/yunxiao/", "language": "zh", "type": "doc", "level": "beginner", "title": "阿里云云效文档（DevOps/流水线，中文）"},
    ],
    "devops": [
        {"url": "https://help.aliyun.com/zh/yunxiao/", "language": "zh", "type": "doc", "level": "beginner", "title": "阿里云云效 DevOps 平台文档（中文）"},
    ],
    "serverless": [
        {"url": "https://help.aliyun.com/zh/fc/", "language": "zh", "type": "doc", "level": "intermediate", "title": "阿里云函数计算 FC 文档（Serverless，中文）"},
    ],
    "lambda": [
        {"url": "https://help.aliyun.com/zh/fc/", "language": "zh", "type": "doc", "level": "intermediate", "title": "阿里云函数计算文档（中文，同类 Serverless）"},
    ],
    "cybersecurity": [
        {"url": "https://www.freebuf.com/", "language": "zh", "type": "doc", "level": "intermediate", "title": "FreeBuf（知名中文网络安全社区）"},
    ],
    "penetration-testing": [
        {"url": "https://www.freebuf.com/", "language": "zh", "type": "doc", "level": "advanced", "title": "FreeBuf 渗透测试专栏（中文社区）"},
    ],
    "nosql": [
        {"url": "https://www.ibm.com/cn-zh/topics/nosql-databases", "language": "zh", "type": "doc", "level": "beginner", "title": "IBM：NoSQL 数据库（中文）"},
    ],
    "edge-computing": [
        {"url": "https://www.ibm.com/cn-zh/topics/edge-computing", "language": "zh", "type": "doc", "level": "beginner", "title": "IBM：什么是边缘计算（中文）"},
    ],
    "high-availability": [
        {"url": "https://www.ibm.com/cn-zh/topics/high-availability", "language": "zh", "type": "doc", "level": "intermediate", "title": "IBM：什么是高可用（中文）"},
    ],
    "load-balancing": [
        {"url": "https://www.ibm.com/cn-zh/topics/load-balancing", "language": "zh", "type": "doc", "level": "intermediate", "title": "IBM：什么是负载均衡（中文）"},
    ],
    "zero-trust": [
        {"url": "https://www.ibm.com/cn-zh/topics/zero-trust", "language": "zh", "type": "doc", "level": "intermediate", "title": "IBM：什么是零信任（中文）"},
    ],
    "time-series": [
        {"url": "https://www.ibm.com/cn-zh/topics/time-series", "language": "zh", "type": "doc", "level": "intermediate", "title": "IBM：时间序列分析（中文）"},
    ],
    "microsoft-office": [
        {"url": "https://support.microsoft.com/zh-cn/office", "language": "zh", "type": "doc", "level": "beginner", "title": "Microsoft Office 支持（中文）"},
    ],
    "jetpack-compose": [
        {"url": "https://developer.android.google.cn/jetpack/compose", "language": "zh", "type": "doc", "level": "intermediate", "title": "Jetpack Compose 官方文档（中文镜像）"},
    ],
    "android": [
        {"url": "https://developer.android.google.cn/guide", "language": "zh", "type": "doc", "level": "beginner", "title": "Android 开发者指南（中文镜像）"},
    ],
    "shell": [
        {"url": "https://www.runoob.com/linux/linux-shell.html", "language": "zh", "type": "tutorial", "level": "beginner", "title": "菜鸟教程：Shell 编程"},
    ],
    "distributed-systems": [
        {"url": "https://xiaolincoding.com/", "language": "zh", "type": "tutorial", "level": "intermediate", "title": "小林 coding：图解分布式/网络/系统（中文）"},
    ],
    "caching": [
        {"url": "https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Caching", "language": "zh", "type": "doc", "level": "intermediate", "title": "MDN：HTTP 缓存（中文）"},
    ],
    "data-warehouse": [
        {"url": "https://www.ibm.com/cn-zh/topics/data-warehouse", "language": "zh", "type": "doc", "level": "beginner", "title": "IBM：什么是数据仓库（中文）"},
    ],
    "data-lake": [
        {"url": "https://www.ibm.com/cn-zh/topics/data-lake", "language": "zh", "type": "doc", "level": "beginner", "title": "IBM：什么是数据湖（中文）"},
    ],
    "sem": [
        {"url": "https://skillshop.withgoogle.com/", "language": "en", "type": "course", "level": "beginner", "title": "Google Skillshop（Ads 官方免费课程）"},
    ],
    "blockchain": [
        {"url": "https://learnblockchain.cn/", "language": "zh", "type": "doc", "level": "intermediate", "title": "登链社区（中文区块链/Web3 学习）"},
    ],
    "github-actions": [
        {"url": "https://docs.github.com/zh/actions", "language": "zh", "type": "doc", "level": "beginner", "title": "GitHub Actions 官方文档（中文）"},
    ],
    "react-native": [
        {"url": "https://reactnative.cn/", "language": "zh", "type": "doc", "level": "intermediate", "title": "React Native 中文文档（社区）"},
    ],
    "iot": [
        {"url": "https://help.aliyun.com/zh/iot/", "language": "zh", "type": "doc", "level": "intermediate", "title": "阿里云物联网平台文档（中文）"},
    ],
    "bigquery": [
        {"url": "https://cloud.google.com/bigquery/docs?hl=zh-cn", "language": "zh", "type": "doc", "level": "intermediate", "title": "Google BigQuery 官方文档（中文）"},
    ],
    "tool-calling": [
        {"url": "https://help.aliyun.com/zh/model-studio/", "language": "zh", "type": "doc", "level": "intermediate", "title": "阿里云百炼 Function Calling 文档（中文）"},
    ],
    "embedding": [
        {"url": "https://help.aliyun.com/zh/dashscope/developer-reference/text-embedding-api-details", "language": "zh", "type": "doc", "level": "intermediate", "title": "阿里云百炼文本 Embedding API（中文）"},
    ],
    "microservices": [
        {"url": "https://www.ibm.com/cn-zh/topics/microservices", "language": "zh", "type": "doc", "level": "intermediate", "title": "IBM：什么是微服务（中文）"},
    ],
    "milvus": [
        {"url": "https://milvus.io/zh/docs", "language": "zh", "type": "doc", "level": "intermediate", "title": "Milvus 官方文档（中文）"},
        {"url": "https://github.com/milvus-io/bootcamp", "language": "en", "type": "project", "level": "intermediate", "title": "Milvus Bootcamp（官方实战项目集）"},
    ],
    "coze": [
        {"url": "https://www.coze.com/docs", "language": "en", "type": "doc", "level": "beginner", "title": "Coze 官方文档（国际版）"},
        {"url": "https://github.com/coze-dev/coze-py", "language": "en", "type": "project", "level": "intermediate", "title": "Coze 官方 Python SDK 仓库"},
    ],
    "groovy": [
        {"url": "https://groovy.apache.org/", "language": "en", "type": "doc", "level": "beginner", "title": "Apache Groovy 官方文档"},
    ],
    "clojure": [
        {"url": "https://clojure.org/guides/getting_started", "language": "en", "type": "doc", "level": "beginner", "title": "Clojure 官方入门指南"},
    ],
    "crf": [
        {"url": "https://sklearn-crfsuite.readthedocs.io/", "language": "en", "type": "doc", "level": "advanced", "title": "sklearn-crfsuite 文档（条件随机场 CRF）"},
    ],
    "gis": [
        {"url": "https://docs.qgis.org/latest/en/docs/", "language": "en", "type": "doc", "level": "beginner", "title": "QGIS 官方文档（开源 GIS 平台）"},
    ],
}

# ---------------------------------------------------------------------------
# YouTube 公认优质免费课程/频道（不爬搜索，仅收录稳定落地链接）
# skill_ids 为显式映射；type 均为 video
# ---------------------------------------------------------------------------
YOUTUBE_CURATED = [
    {"url": "https://www.youtube.com/watch?v=rfscVS0vtbw", "title": "Python for Everybody (freeCodeCamp 完整课程)",
     "skill_ids": ["python"], "language": "en", "community_hint": "freeCodeCamp 爆款全课程"},
    {"url": "https://www.youtube.com/watch?v=PKfxmFU3lWY", "title": "JavaScript Programming - Full Course (freeCodeCamp)",
     "skill_ids": ["javascript"], "language": "en", "community_hint": "freeCodeCamp 爆款全课程"},
    {"url": "https://www.youtube.com/watch?v=aircAruvnK4", "title": "But what is a neural network? | Deep Learning Chapter 1 (3Blue1Brown)",
     "skill_ids": ["deep-learning", "machine-learning"], "language": "en", "community_hint": "3Blue1Brown 神级可视化"},
    {"url": "https://www.youtube.com/@freecodecamp", "title": "freeCodeCamp.org 官方频道（全免费长课程）",
     "skill_ids": ["javascript", "python", "html-css", "data-science"], "language": "en", "community_hint": "960万+订阅"},
    {"url": "https://www.youtube.com/@coreyms", "title": "Corey Schafer 频道（Python 教程）",
     "skill_ids": ["python"], "language": "en", "community_hint": "知名 Python 教育频道"},
    {"url": "https://www.youtube.com/@TraversyMedia", "title": "Traversy Media 频道（Web 开发）",
     "skill_ids": ["javascript", "react", "html-css"], "language": "en", "community_hint": "知名 Web 开发频道"},
    {"url": "https://www.youtube.com/@fireship", "title": "Fireship 频道（现代 Web/AI 快览）",
     "skill_ids": ["javascript", "agent", "aigc"], "language": "en", "community_hint": "知名开发资讯频道"},
    {"url": "https://www.youtube.com/@statquest", "title": "StatQuest 频道（统计与机器学习）",
     "skill_ids": ["machine-learning", "statistics", "deep-learning"], "language": "en", "community_hint": "ML 统计教学经典频道"},
    {"url": "https://www.youtube.com/@3blue1brown", "title": "3Blue1Brown 频道（数学可视化）",
     "skill_ids": ["machine-learning", "deep-learning", "transformer"], "language": "en", "community_hint": "数学可视化顶级频道"},
    {"url": "https://www.youtube.com/@sentdex", "title": "sentdex 频道（Python/机器学习实战）",
     "skill_ids": ["python", "machine-learning"], "language": "en", "community_hint": "老牌 Python ML 频道"},
    {"url": "https://www.youtube.com/@GoogleCloudTech", "title": "Google Cloud Tech 官方频道",
     "skill_ids": ["gcp", "bigquery", "data-engineering"], "language": "en", "community_hint": "官方频道"},
    {"url": "https://www.youtube.com/@awsdevelopers", "title": "AWS Developers 官方频道",
     "skill_ids": ["aws"], "language": "en", "community_hint": "官方频道"},
]

# ---------------------------------------------------------------------------
# B 站知名 UP 主空间/官方账号（不爬搜索 API——无登录态会被风控；
# 仅收录经确认的知名教学 UP 主空间链接，运行时可达性逐一验证）
# ---------------------------------------------------------------------------
BILIBILI_CURATED = [
    {"url": "https://space.bilibili.com/302417610", "title": "尚硅谷（Java/前端/大数据 免费系统课程）",
     "skill_ids": ["java", "javascript", "mysql", "spring", "springboot", "hadoop", "spark", "linux", "html-css"], "language": "zh", "community_hint": "知名 IT 培训机构官方账号"},
    {"url": "https://space.bilibili.com/37974444", "title": "黑马程序员（Python/Java/前端 免费系统课程）",
     "skill_ids": ["python", "java", "c", "cpp", "html-css", "javascript", "linux"], "language": "zh", "community_hint": "知名 IT 培训机构官方账号"},
    {"url": "https://space.bilibili.com/243821484", "title": "莫烦Python（Python/机器学习 经典教程）",
     "skill_ids": ["python", "machine-learning", "reinforcement-learning"], "language": "zh", "community_hint": "知名 Python 教育 UP 主"},
    {"url": "https://space.bilibili.com/88461692", "title": "3Blue1Brown 官方账号（数学/深度学习可视化，中文字幕）",
     "skill_ids": ["machine-learning", "deep-learning", "transformer", "linear-algebra"], "language": "zh", "community_hint": "官方中文字幕账号"},
    {"url": "https://space.bilibili.com/1567748478", "title": "跟李沐学AI（动手学深度学习配套视频）",
     "skill_ids": ["deep-learning", "machine-learning", "pytorch", "llm"], "language": "zh", "community_hint": "李沐老师官方账号"},
    {"url": "https://space.bilibili.com/34786453", "title": "程序员鱼皮（编程学习路线/项目实战）",
     "skill_ids": ["java", "springboot", "project-management"], "language": "zh", "community_hint": "知名编程学习 UP 主"},
]

# B 站 skill 别名中的 linear-algebra 不在词表，会被过滤（代码里做存在性校验）

# ---------------------------------------------------------------------------
# freeCodeCamp 认证 -> 技能 显式映射（认证 slug 从 curriculum yml 解析后使用）
# ---------------------------------------------------------------------------
FCC_SKILL_OVERRIDES = {
    "responsive-web-design": ["html", "css"],
    "javascript-algorithms-and-data-structures": ["javascript", "algorithms", "data-structures"],
    "front-end-development-libraries": ["react", "redux", "bootstrap", "jquery", "sass"],
    "data-visualization": ["data-visualization", "javascript"],
    "relational-database": ["sql-lang", "postgresql"],
    "back-end-development-and-apis": ["nodejs", "express", "mongodb"],
    "quality-assurance": ["qa-automation", "qa-testing", "nodejs", "express"],
    "scientific-computing-with-python": ["python"],
    "data-analysis-with-python": ["pandas", "numpy", "data-analysis", "python"],
    "information-security": ["cybersecurity"],
    "machine-learning-with-python": ["machine-learning", "tensorflow", "numpy"],
    "college-algebra-with-python": ["python"],
    "full-stack-developer": ["html-css", "javascript", "react", "nodejs", "sql-lang"],
    "foundational-c-sharp-with-microsoft": ["csharp", "dotnet"],
    "a2-english-for-developers": [],
    "b1-english-for-developers": [],
}

# ---------------------------------------------------------------------------
# 各源权威度基线（quality_score 的"来源权威性"维度输入）
# ---------------------------------------------------------------------------
SOURCE_AUTHORITY = {
    # 官方文档 / 顶级机构
    "official_doc": 1.0,
    "mdn": 0.98,
    "university": 0.95,
    # 知名教育组织 / 顶星社区项目
    "freecodecamp": 0.93,
    "ossu": 0.92,
    "github_awesome": 0.90,
    "cs_self_learning": 0.88,
    # MOOC 平台（知名高校/企业课程）
    "coursera": 0.85,
    # 知名视频平台官方/头部账号
    "youtube_curated": 0.82,
    "bilibili_curated": 0.80,
    # 中文主流教程站
    "runoob": 0.72,
    # roadmap.sh 社区精选
    "roadmap_official": 0.78,
    "roadmap_course": 0.74,
    "roadmap_video": 0.66,
    "roadmap_article": 0.62,
    "roadmap_unknown": 0.55,
}
