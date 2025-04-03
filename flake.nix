{
  description = "Todord distributed by Nix.";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pythonBasics =  pkgs.python3.withPackages (ps: with ps; [
          discordpy
        ]);
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          discordpy
          ruff
        ]);
      in
      {
        packages = {
          todord = pkgs.stdenv.mkDerivation {
            pname = "todord";
            version = "0.0.1";
            src = ./.;

            nativeBuildInputs = [ pkgs.makeWrapper ];
            buildInputs = [ pythonBasics pkgs.git ];

            dontBuild = true;

            installPhase = ''
              echo "Contents of source directory:"
              ls -la
              mkdir -p $out/bin $out/lib
              if [ -f "todord.py" ]; then
                cp todord.py $out/lib/
                makeWrapper ${pythonBasics}/bin/python $out/bin/todord \
                  --add-flags "$out/lib/todord.py" \
                  --prefix PATH : ${pkgs.git}/bin
              else
                echo "ERROR: todord.py not found, adding it..."
                exit 1
              fi
            '';

            shellHook = ''
              export PATH=${pythonBasics}/bin:${pkgs.git}/bin:$PATH
            '';
          };
          
          default = self.packages.${system}.todord;
        };

        apps = {
          todord = {
            type = "app";
            program = "${self.packages.${system}.todord}/bin/todord";
            meta = {
              description = "Todord application";
              mainProgram = "todord";
            };
          };
          
          default = self.apps.${system}.todord;
        };

        devShells = {
          default = pkgs.mkShell {
            name = "todord-dev-env";
            packages = [ pythonEnv pkgs.git ];
            
            # Don't automatically run the todord package to prevent auto-execution
            # Instead make it available on PATH only
            shellHook = ''
              export HISTFILE=$HOME/.history_nix
              export PYTHONPATH=$PYTHONPATH:$(pwd)
              
              export PATH=${pythonEnv}/bin:${pkgs.git}/bin:$PATH
              
              alias todord="python $(pwd)/todord.py"
              
              echo "Todord development environment activated"
              echo "Type 'todord' to run the application"
            '';
          };
        };
      });
}
