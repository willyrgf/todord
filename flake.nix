{
  description = "Todord distributed by Nix.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";

    # Syng
    syng.url = "github:willyrgf/syng?rev=3de4cac46faf3ea97332b60d21eb752414cc0867";
  };

  outputs = { self, nixpkgs, flake-utils, syng }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pythonWithPkgs =
          pkgs.python3.withPackages (ps: with ps; [ discordpy ruff ]);
        
        # Define app name and version as variables
        appName = "todord";
        appVersion = "0.1.0";
        
        # Import syng package
        syngPkg = syng.packages.${system}.default;
      in {
        packages = {
          todord = pkgs.stdenv.mkDerivation {
            pname = appName;
            version = appVersion;
            src = self;

            nativeBuildInputs = [ pkgs.makeWrapper ];
            buildInputs = [ pythonWithPkgs pkgs.git ];

            dontBuild = true;

            installPhase = ''
              mkdir -p $out/bin $out/lib
              if [ -f "$src/todord.py" ]; then
                cp $src/todord.py $out/lib/todord.py
                makeWrapper ${pythonWithPkgs}/bin/python $out/bin/todord \
                  --add-flags "$out/lib/todord.py" \
                  --prefix PATH : ${pkgs.git}/bin \
                  --set TODORD_APP_NAME "${appName}" \
                  --set TODORD_APP_VERSION "${appVersion}"
              else
                echo "ERROR: todord.py not found in source directory" >&2
                exit 1
              fi
            '';
          };

          todord-syng = pkgs.writeShellScriptBin "todord-syng" ''
            #!/usr/bin/env bash
            
            # Capture the SSH Auth Socket from the invoking environment
            INVOKING_SSH_AUTH_SOCK="''${SSH_AUTH_SOCK}"
            
            # Function to display usage
            usage() {
              echo "Usage: todord-syng [--data_dir PATH]"
              echo "  --data_dir PATH    Specify the data directory (default: ./data)"
              echo ""
              echo "Environment variables:"
              echo "  DISCORD_TOKEN      Required: Discord bot token"
              echo "  SSH_AUTH_SOCK      Optional: Forwarded if set in invoking environment"
              exit 1
            }
            
            # Parse arguments
            DATA_DIR="./data"
            
            while [[ $# -gt 0 ]]; do
              case "$1" in
                --data_dir)
                  DATA_DIR="$2"
                  shift 2
                  ;;
                --help|-h)
                  usage
                  ;;
                *)
                  echo "Unknown option: $1"
                  usage
                  ;;
              esac
            done
            
            # Check if DISCORD_TOKEN is set
            if [ -z "''${DISCORD_TOKEN}" ]; then
              echo "ERROR: DISCORD_TOKEN environment variable must be set"
              usage
            fi
            
            # Create the directory if it doesn't exist
            mkdir -p "$DATA_DIR"
            
            # Function to clean up all background processes
            cleanup() {
              echo "Cleaning up background processes..."
              # Check if PIDs exist before killing to avoid errors
              [[ -n "$SYNG_AUTO_PULL_PID" ]] && kill -0 $SYNG_AUTO_PULL_PID 2>/dev/null && kill $SYNG_AUTO_PULL_PID
              [[ -n "$SYNG_COMMIT_PUSH_PID" ]] && kill -0 $SYNG_COMMIT_PUSH_PID 2>/dev/null && kill $SYNG_COMMIT_PUSH_PID
              [[ -n "$TODORD_PID" ]] && kill -0 $TODORD_PID 2>/dev/null && kill $TODORD_PID
              echo "Cleanup finished."
            }

            # Set trap to call cleanup function on exit signals
            trap cleanup EXIT SIGINT SIGTERM
            
            # Export the SSH Auth Socket if it was set
            if [ -n "$INVOKING_SSH_AUTH_SOCK" ]; then
              export SSH_AUTH_SOCK="$INVOKING_SSH_AUTH_SOCK"
              echo "Forwarding SSH_AUTH_SOCK: $SSH_AUTH_SOCK"
            else
              echo "Warning: SSH_AUTH_SOCK not set in invoking environment. Git operations requiring SSH agent may fail."
            fi

            # Start processes in the background
            echo "Starting syng with auto-pull in background..."
            ${syngPkg}/bin/syng --source_dir "$DATA_DIR" --git_dir "$DATA_DIR" --auto-pull &
            SYNG_AUTO_PULL_PID=$!
            
            echo "Starting syng with commit-push in background..."
            ${syngPkg}/bin/syng --source_dir "$DATA_DIR" --git_dir "$DATA_DIR" --commit-push --per-file &
            SYNG_COMMIT_PUSH_PID=$!
            
            echo "Starting todord with data directory: $DATA_DIR in background..."
            ${self.packages.${system}.todord}/bin/todord --data_dir "$DATA_DIR" &
            TODORD_PID=$!

            # Wait for the main todord process to finish
            echo "Waiting for todord (PID: $TODORD_PID) to exit..."
            wait $TODORD_PID
            TODORD_EXIT_CODE=$?
            echo "todord exited with code $TODORD_EXIT_CODE."
            
            # Explicit cleanup is handled by the EXIT trap when wait returns or script exits

            # Exit with the todord exit code
            exit $TODORD_EXIT_CODE
          '';

          default = self.packages.${system}.todord;
        };

        apps = {
          todord = {
            type = "app";
            program = "${self.packages.${system}.todord}/bin/todord";
            meta = with pkgs.lib; {
              description = "A To Do List Discord Bot";
              homepage = "https://github.com/willyrgf/todord";
              license = licenses.mit;
              platforms = platforms.all;
            };
          };
          
          todord-syng = {
            type = "app";
            program = "${self.packages.${system}.todord-syng}/bin/todord-syng";
            meta = with pkgs.lib; {
              description = "A To Do List Discord Bot with Git Synchronization";
              homepage = "https://github.com/willyrgf/todord";
              license = licenses.mit;
              platforms = platforms.all;
            };
          };

          default = self.apps.${system}.todord;
        };

        devShells = {
          default = pkgs.mkShell {
            name = "todord-dev-env";
            packages = [ pythonWithPkgs pkgs.git syngPkg ];

            shellHook = ''
              export HISTFILE=$HOME/.history_nix
              export PYTHONPATH=${builtins.toString ./.}:$PYTHONPATH
              export PATH=${pythonWithPkgs}/bin:${pkgs.git}/bin:$PATH
              export TODORD_APP_NAME="${appName}"
              export TODORD_APP_VERSION="${appVersion}"
              alias todord="python ${builtins.toString ./.}/todord.py"
              alias todord-syng="${self.packages.${system}.todord-syng}/bin/todord-syng"
              echo "Todord development environment activated"
              echo "Type 'todord' to run the application"
              echo "Type 'todord-syng --data_dir path/to/directory' to run with git sync"
            '';
          };
        };
      });
}
