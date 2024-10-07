#!casa -c
import argparse

def main():
    # Command line options
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', nargs=1, 
            help='Casa parameter.')
    parser.add_argument('concatvis', nargs=1, type=str, 
            help='Concatenated ms name')
    parser.add_argument('uvdata', nargs='*', type=str, 
            help='uv data ms files')
    args = parser.parse_args()
    
    # Concat
    concat(vis=args.uvdata, concatvis=args.concatvis[0])

if __name__=="__main__":
    main()
