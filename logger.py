import os
import logging
import logging.handlers

def get_logger(name, file_name='debug.log', **kwargs):
    """Creates a new logger.

    Parameters:
        name (str): name of the logger.
        file_name (str): file name of the log.
    Keywords:
        filelevel (default=logging.DEBUG): logging to file level.
        stdoutlevel (default=logging.INFO): logging to std output level.
        filefmt (str, default=%(asctime)s - %(name)s - %(levelname)s: %(message)s): 
            logging to file message format.
        stdoutfmt (str, default=%(levelname)s: %(message)s): 
            logging to std output message format.
        maxBytes (int, default=5MB): maximum size of logging file in bytes.
        backupCount (int, default=5): maximum number of log files to rotate.
    """
    # Create logger
    logger = logging.getLogger(name)
    if not len(logger.handlers):
        logger.setLevel(kwargs.get('filelevel', logging.DEBUG))

        # File handler
        file_name = os.path.expanduser(file_name)
        filefmt = '%(asctime)s [%(levelname)s] - %(filename)s '+\
                '(%(funcName)s:%(lineno)s): %(message)s'
        fh = logging.handlers.RotatingFileHandler(file_name,
                maxBytes=kwargs.get('maxBytes',5242880),
                backupCount=kwargs.get('backupCount',5))
        fh.setLevel(kwargs.get('filelevel', logging.DEBUG))
        fh.setFormatter(logging.Formatter(kwargs.get('filefmt', filefmt)))
        #fh.setFormatter(logging.Formatter(kwargs.get('filefmt', 
        #    '%(asctime)s - %(name)s - %(levelname)s: %(message)s')))

        # Stream handler
        sh = logging.StreamHandler()
        sh.setLevel(kwargs.get('stdoutlevel', logging.INFO))
        sh.setFormatter(logging.Formatter(kwargs.get('stdoutfmt', 
            '%(levelname)s: %(message)s')))

        # Register handlers
        logger.addHandler(fh)
        logger.addHandler(sh)

    return logger

