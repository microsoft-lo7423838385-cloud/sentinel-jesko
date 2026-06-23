param (
    [int]$debug = 1
)

# Get the script's parent directory (the project root)
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
log -out "Project root set to: $projectRoot" -type info

function log{
    param (
        [string]$out,
        [string]$type = "log"
    )
    switch($type){
        "log" {
            if($script:debug -eq 1){
                Write-Host "Log: '$out'" -ForegroundColor Magenta
            }
        }
        "info" {
            Write-Host "Info: '$out'" -ForegroundColor Blue
        }
        "error" {
            Write-Host "Error: '$out'" -ForegroundColor Red
        }
        "success" {
            Write-Host "Success: '$out'" -ForegroundColor Green
        }
        Default {
            Write-Output $out
        }
    }
}

function downloadSamePath {
    param (
        [string]$url
    )
    $name = [System.IO.Path]::GetFileName($url)
    $dPath = Join-Path -Path (Get-Location) -ChildPath ".downloads"`
    ##create output directory if it doesn't exist
    if(-Not (Test-Path -Path $dPath -PathType Container)){
         New-Item -Path $dPath -ItemType Directory > $null
         log -out "New Directory Created: $dPath"
    }
    $finalPath = Join-Path -Path $dPath -ChildPath $name
    try {
        Invoke-webrequest -Uri $url -Outfile $finalPath > $null
    }
    catch {
        log -out "Error downloading '$url' to '$finalPath'" -type error
        exit
    }
    if(-Not (Test-Path -Path $finalPath -PathType Leaf)){
       log -out "File '$name' downloaded not found in '$finalPath'" 
    }
    else {
        log -out "File '$name' downloaded successfully to '$finalPath'"
    }

    return $finalPath;
}

function runSilent{
    param(
        [string]$path,
        [string]$arg
    )
	if(-Not ($arg)){
		Write-Output "Args is not given"
		exit
	}
    if(-Not (Test-Path -Path $path -PathType Leaf)){
        ##file does not exist
        log -out "File '$path' not found to be executed"
		exit
    }
    ##file exists
    try {
        Start-Process -FilePath $path -ArgumentList $arg -Wait
        log -out "Process '$path' execution complete no errors"
        #reload envronment variables against modified path
        log -out "Reloading PATH. A new terminal may be required for changes to take effect." -type info
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine")
        return 1
    }
    catch {
		Write-Output $_
        log -out "Error executing '$path'" -type error
        exit
    }


}

function installComponent{
    param (
        [string]$component
    )
    switch ($component) {
        "python" { 
			log -out "Downloading Python" -type info
            $url = "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
            $file = downloadSamePath -url $url
            if(-Not ($file)){
                ##bad file
                log -out "Error Downloading Python" -type error
            }
            else{
                log -out "Installing python ..." -type info
                runSilent -path $file -arg "/passive InstallAllUsers=1 PrependPath=1 InstallLauncherAllUsers=1"
                log -out "Python installed" -type success
            }
        }
        "git" {
			log -out "Downloading Git" -type info
            $url = "https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe"
            $file = downloadSamePath -url $url
            if(-Not ($file)){
                ##bad file
                log -out "Error Downloading Git" -type error
            }
            else{
                log -out "Installing Git ..." -type info
                runSilent -path $file -arg "/SILENT /NORESTART"
                log -out "Git installed" -type success
            }
        }
        "node" {
			log -out "Downloading Node" -type info
            $url = "https://nodejs.org/dist/v22.4.1/node-v22.4.1-x64.msi"
            $file = downloadSamePath -url $url
            if(-Not ($file)){
                ##bad file
                log -out "Error Downloading Node" -type error
            }
            else{
                log -out "Installing Node ..." -type info
                runSilent -path $file -arg "/passive"
                log -out "Node installed" -type success
            }
        }
        Default {
            Write-Output "Component '$component' not found"
        }
    }

}

#install git or ensure it's installed
try{
    Get-Command git | Out-Null
	log -out "Git is installed!" -type info
}
catch{
    ##git is not found
    ##install git
    installComponent -Component "git"
    try {
        # Verify installation and that it's in the path
        Get-Command git | Out-Null
        log -out "Git successfully installed and found in PATH." -type success
    } catch {
        log -out "Git was installed, but not found in PATH. Please open a new terminal and re-run." -type error
        exit
    }
}

#install python or ensure it's installed
try{
    # Check if py launcher can find the specific version
    py -3.12 -c "import sys; print(sys.version)" | Out-Null
	log -out "Python 3.12 is installed and accessible via py launcher." -type info
}
catch{
    #py launcher is not installed or 3.12 is not found, install it
    installComponent -Component "python"
    try {
        py -3.12 -c "import sys; print(sys.version)" | Out-Null
        log -out "Python 3.12 successfully installed." -type success
    } catch {
        log -out "Python was installed, but 'py -3.12' is not working. Please open a new terminal and re-run." -type error
        exit
    }
}

## All components installed. Now set up the local environment.

# 1. Create Python Virtual Environment
if (-Not (Test-Path -Path ".venv" -PathType Container)) {
    log -out "Creating Python virtual environment..." -type info
    py -3.12 -m venv .venv
    log -out "Virtual environment created." -type success
}

# 2. Activate virtual environment and install Python dependencies
log -out "Installing Python dependencies..." -type info
$pipPath = Join-Path -Path $projectRoot -ChildPath ".venv\Scripts\pip.exe"
# Use the cleaned, consolidated requirements file from the project root
$requirementsPath = Join-Path -Path $projectRoot -ChildPath "requirements.txt"
& $pipPath install -r $requirementsPath

log -out "Python setup complete." -type success

# 3. Create placeholder files if they don't exist
$recipientsFile = Join-Path -Path $projectRoot -ChildPath "recipients.txt"
if (-Not (Test-Path -Path $recipientsFile)) {
    log -out "Creating empty 'recipients.txt' file." -type info
    New-Item -Path $recipientsFile -ItemType File > $null
}

##write-output
write-Host ""
write-Host ""
Write-Host "Project setup is complete in '$projectRoot'" -ForegroundColor Green
Write-Host "Your sender is ready to use" -ForegroundColor Green
Write-Host "To run, use the 'run.bat' script for the main menu." -ForegroundColor Green

## Clean up
if(Test-Path -Path ".downloads" -PathType Container){
	log -out "Cleaning up downloaded files..." -type info
	Remove-Item ".downloads" -Recurse -Force
}

Pop-Location

##open needed folder
try{
	Start-Process .
}
catch{
	
}
