@echo off
setlocal
set "JAVA_HOME=%~dp0..\allure-local\java17\jdk-17.0.19+10-jre"
set "PATH=%JAVA_HOME%\bin;%PATH%"
call "%~dp0..\allure-local\allure-cli\allure-2.42.0\bin\allure.bat" %*
