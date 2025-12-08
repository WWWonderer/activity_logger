set appName to ""
set windowTitle to ""
set windowURL to ""

-- Get frontmost app name and generic window title
try
    tell application "System Events"
        set frontProc to first process whose frontmost is true
        set appName to name of frontProc
        if (count of windows of frontProc) > 0 then
            set windowTitle to name of front window of frontProc
        end if
    end tell
on error
    set windowTitle to "Unknown Window"
    return appName & "||" & windowTitle & "||" & windowURL
end try

if appName is "Safari" then 
    try
        tell application "Safari"
            if (count of windows) > 0 then
                set frontWindow to front window
                set windowTitle to name of current tab of frontWindow
                set windowURL to URL of current tab of frontWindow
            end if
        end tell
    end try
end if

if windowTitle is "" then
    set windowTitle to "Unknown Window"
end if 

if windowURL is missing value then
    set windowURL to ""
end if

return appName & "||" & windowTitle & "||" & windowURL