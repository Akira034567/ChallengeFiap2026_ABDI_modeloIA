$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
npm --prefix frontend install
npm --prefix frontend run dev

