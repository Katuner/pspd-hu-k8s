$env:BASE_URL = "https://kiriland.unb.br/grupo5"

Write-Host "========================================="
Write-Host "Iniciando o teste de carga K6 (Fase B)"
Write-Host "========================================="
Write-Host ""
Write-Host "Vá abrindo o Grafana: https://grafana.kiriland.unb.br"
Write-Host "Usuário: admgrp05 | Senha: 123456"
Write-Host ""

$vus = Read-Host "Quantos usuários simultâneos você quer simular? (ex: 10, 50, 100)"

Write-Host "Rodando teste com $vus usuários..."
.\k6.exe run -e VUS=$vus -e BASE_URL=$env:BASE_URL -e DURATION=1m load-tests\k6-load.js

Write-Host "Teste finalizado!"
Write-Host "Pressione qualquer tecla para sair..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
