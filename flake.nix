{
  description = "Todord distributed by Nix.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pythonWithPkgs =
          pkgs.python3.withPackages (ps: with ps; [ discordpy ruff ]);
        
        # Define app name and version as variables
        appName = "todord";
        appVersion = "0.1.0";
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

          default = self.apps.${system}.todord;
        };

        devShells = {
          default = pkgs.mkShell {
            name = "todord-dev-env";
            packages = [ pythonWithPkgs pkgs.git ];

            shellHook = ''
              export HISTFILE=$HOME/.history_nix
              export PYTHONPATH=${builtins.toString ./.}:$PYTHONPATH
              export PATH=${pythonWithPkgs}/bin:${pkgs.git}/bin:$PATH
              export TODORD_APP_NAME="${appName}"
              export TODORD_APP_VERSION="${appVersion}"
              alias todord="python ${builtins.toString ./.}/todord.py"
              echo "Todord development environment activated"
              echo "Type 'todord' to run the application"
            '';
          };
        };
      });
}
